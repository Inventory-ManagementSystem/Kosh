import hashlib
import hmac
import json
import logging
import re
import uuid
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from notifications import events
from suppliers.models import SupplierPayoutAccount

from .models import OwnerRefund, Payment, Payout, SupplierDebt
from .payment_services import to_paise

logger = logging.getLogger(__name__)

API_BASE = "https://api.razorpay.com/v1"
TIMEOUT_SECONDS = 20
IMPS_LIMIT_PAISE = 500_000_00 
UPI_LIMIT_PAISE = 100_000_00  

IN_FLIGHT = {"queued", "pending", "scheduled", "processing"}
FAILED_STATES = {"failed", "reversed", "rejected", "cancelled"}


class PayoutError(Exception):
  def __init__(self, message, code, retryable=False):
    super().__init__(message)
    self.message = message
    self.code = code
    self.retryable = retryable


class PayoutWebhookError(Exception):
  pass

def _auth():
  key = getattr(settings, "RAZORPAYX_KEY_ID", "") or settings.RAZORPAY_KEY_ID
  secret = getattr(settings, "RAZORPAYX_KEY_SECRET", "") or settings.RAZORPAY_KEY_SECRET
  if not (key and secret and getattr(settings, "RAZORPAYX_ACCOUNT_NUMBER", "")):
    raise PayoutError(
      "Supplier payouts aren't set up yet.", "PAYOUTS_NOT_CONFIGURED", retryable=True
    )
  return key, secret


def _call(method, path, body=None, headers=None):
  auth = _auth()
  try:
    resp = requests.request(
      method, API_BASE + path, auth=auth, json=body, headers=headers, timeout=TIMEOUT_SECONDS
    )
  except requests.RequestException as err:
    logger.warning("RazorpayX %s %s failed: %s", method, path, err)
    raise PayoutError(
      "Couldn't reach RazorpayX. Try again in a minute.", "GATEWAY_ERROR", retryable=True
    ) from err

  try:
    data = resp.json()
  except ValueError:
    data = {}
  if resp.status_code == 429 or resp.status_code >= 500:
    raise PayoutError(
      "RazorpayX is having trouble. Try again in a minute.", "GATEWAY_ERROR", retryable=True
    )
  if resp.status_code >= 400:
    error = data.get("error") or {}
    logger.warning("RazorpayX %s %s -> %s %s", method, path, resp.status_code, error)
    raise PayoutError(
      error.get("description") or f"RazorpayX rejected the request ({resp.status_code}).",
      "GATEWAY_REJECTED",
    )
  return data


def _contact_name(supplier):
  name = re.sub(r"\s+", " ", supplier.company_name).strip()[:50]
  name = re.sub(r"[^A-Za-z0-9.]+$", "", name) 
  return name if len(name) >= 3 else f"Supplier {str(supplier.pk)[:8]}"


def _create_contact(supplier):
  contact = _call("POST", "/contacts", {
    "name": _contact_name(supplier),
    "email": supplier.user.email,
    "contact": supplier.phone,
    "type": "vendor",
    "reference_id": str(supplier.pk),
    "notes": {"kosh_supplier_id": str(supplier.pk)},
  })
  return contact["id"]


def save_payout_account(supplier, data):
  account = SupplierPayoutAccount.objects.filter(supplier_profile=supplier).first()
  contact_id = account.razorpay_contact_id if account else _create_contact(supplier)

  if data["method"] == SupplierPayoutAccount.Method.BANK_ACCOUNT:
    fund = _call("POST", "/fund_accounts", {
      "contact_id": contact_id,
      "account_type": "bank_account",
      "bank_account": {
        "name": data["account_holder_name"],
        "ifsc": data["ifsc"],
        "account_number": data["account_number"],
      },
    })
    details = {
      "account_holder_name": data["account_holder_name"],
      "ifsc": data["ifsc"],
      "bank_name": (fund.get("bank_account") or {}).get("bank_name") or "",
      "account_last4": data["account_number"][-4:],
      "vpa": "",
    }
  else:
    fund = _call("POST", "/fund_accounts", {
      "contact_id": contact_id,
      "account_type": "vpa",
      "vpa": {"address": data["vpa"]},
    })
    details = {
      "account_holder_name": "", "ifsc": "", "bank_name": "", "account_last4": "",
      "vpa": data["vpa"],
    }

  old_fund_id = account.razorpay_fund_account_id if account else None
  with transaction.atomic():
    account, _ = SupplierPayoutAccount.objects.update_or_create(
      supplier_profile=supplier,
      defaults={
        "method": data["method"],
        "razorpay_contact_id": contact_id,
        "razorpay_fund_account_id": fund["id"],
        **details,
      },
    )
    released = release_held_payouts(supplier)

  if old_fund_id and old_fund_id != fund["id"]:
    try:
      _call("PATCH", f"/fund_accounts/{old_fund_id}", {"active": False})
    except PayoutError:
      logger.warning("Couldn't deactivate old fund account %s", old_fund_id)
  return account, released


def release_held_payouts(supplier):
  released = 0
  held = Payout.objects.select_for_update().filter(
    supplier_profile=supplier, status=Payout.Status.ON_HOLD
  )
  for payout in held:
    payout.status = Payout.Status.PENDING
    payout.failure_reason = ""
    payout.save(update_fields=["status", "failure_reason", "updated_at"])
    _enqueue(payout)
    released += 1

  failed = set(
    Payout.objects.filter(supplier_profile=supplier, status=Payout.Status.FAILED)
    .values_list("purchase_order_id", "kind")
  )
  for po_id, kind in failed:
    if Payout.objects.filter(
      purchase_order_id=po_id, kind=kind, status__in=Payout.ACTIVE
    ).exists():
      continue
    last = (
      Payout.objects.filter(purchase_order_id=po_id, kind=kind, status=Payout.Status.FAILED)
      .order_by("-created_at").first()
    )
    retry = Payout.objects.create(
      purchase_order_id=po_id,
      invoice_id=last.invoice_id,
      supplier_profile=supplier,
      kind=kind,
      gross_amount=last.gross_amount,
      deducted_amount=last.deducted_amount,
      amount=last.amount,
      status=Payout.Status.PENDING,
    )
    _enqueue(retry)
    released += 1
  return released


def _enqueue(payout):
  from .tasks import send_advance_payout
  payout_id = str(payout.pk)
  transaction.on_commit(lambda: send_advance_payout.delay(payout_id))


def _recover_debts(supplier_id, gross):
  held_back = Decimal("0")
  taken = []
  debts = SupplierDebt.objects.select_for_update().filter(
    supplier_profile_id=supplier_id, status=SupplierDebt.Status.OPEN
  ).order_by("created_at")
  for debt in debts:
    room = gross - held_back
    if room <= 0:
      break
    part = min(debt.outstanding, room)
    debt.recovered_amount += part
    if debt.recovered_amount >= debt.amount:
      debt.status = SupplierDebt.Status.SETTLED
    debt.save(update_fields=["recovered_amount", "status", "updated_at"])
    held_back += part
    taken.append((debt, part))
  return held_back, taken


def _create_payout(po, invoice, kind, gross):
  if gross <= 0:
    return None
  if Payout.objects.filter(purchase_order=po, kind=kind, status__in=Payout.ACTIVE).exists():
    return None

  held_back, taken = _recover_debts(po.supplier_profile_id, gross)
  net = gross - held_back
  has_account = SupplierPayoutAccount.objects.filter(
    supplier_profile_id=po.supplier_profile_id
  ).exists()

  if net == 0:
    status = Payout.Status.PROCESSED 
  elif has_account:
    status = Payout.Status.PENDING
  else:
    status = Payout.Status.ON_HOLD

  payout = Payout.objects.create(
    purchase_order=po,
    invoice=invoice,
    supplier_profile_id=po.supplier_profile_id,
    kind=kind,
    gross_amount=gross,
    deducted_amount=held_back,
    amount=net,
    status=status,
    processed_at=timezone.now() if net == 0 else None,
  )

  for debt, part in taken:
    advance = Payment.objects.filter(
      purchase_order_id=debt.purchase_order_id,
      kind=Payment.Kind.ADVANCE, status=Payment.Status.PAID,
    ).first()
    if advance is None:
      logger.error("Debt %s has no paid advance to refund", debt.pk)
      continue
    refund = OwnerRefund.objects.create(
      payment=advance, invoice_id=debt.invoice_id, debt=debt, recovered_by=payout,
      source=OwnerRefund.Source.RECOVERED, amount=part,
    )
    _enqueue_refund(refund)

  if status == Payout.Status.PENDING:
    _enqueue(payout)
  elif status == Payout.Status.ON_HOLD:
    transaction.on_commit(lambda: events.payout_on_hold(payout))
  else:
    transaction.on_commit(lambda: events.payout_sent(payout))
  return payout


def create_advance_payout(po, invoice):
  if invoice.advance_applied <= 0:
    return None
  if not Payment.objects.filter(
    purchase_order=po, kind=Payment.Kind.ADVANCE, status=Payment.Status.PAID
  ).exists():
    logger.error("PO %s has an advance on its invoice but no paid payment", po.number)
    return None
  return _create_payout(po, invoice, Payout.Kind.ADVANCE, invoice.advance_applied)


def create_balance_payout(po, invoice):
  return _create_payout(po, invoice, Payout.Kind.BALANCE, invoice.balance_due)


def _enqueue_refund(refund):
  from .tasks import refund_owner
  refund_id = str(refund.pk)
  transaction.on_commit(lambda: refund_owner.delay(refund_id))


def settle_after_receipt(po, invoice):
  if invoice.balance_due <= 0 and invoice.status != invoice.Status.PAID:
    invoice.status = invoice.Status.PAID
    invoice.save(update_fields=["status", "updated_at"])

  payable = invoice.grand_total - invoice.discrepancy_credit
  advance = po.advance_amount
  if payable >= advance:
    return None

  advance_payout = (
    Payout.objects.filter(purchase_order=po, kind=Payout.Kind.ADVANCE)
    .exclude(status=Payout.Status.FAILED).order_by("-created_at").first()
    or Payout.objects.filter(purchase_order=po, kind=Payout.Kind.ADVANCE)
    .order_by("-created_at").first()
  )
  paid_to_supplier = advance_payout.gross_amount if advance_payout else Decimal("0")
  owed_by_supplier = max(paid_to_supplier - payable, Decimal("0"))
  held_by_kosh = (advance - payable) - owed_by_supplier

  debt = None
  if owed_by_supplier > 0:
    debt = SupplierDebt.objects.create(
      supplier_profile_id=po.supplier_profile_id, purchase_order=po,
      invoice=invoice, amount=owed_by_supplier,
    )
    transaction.on_commit(lambda: events.supplier_debt_created(debt))

  if held_by_kosh > 0:
    payment = Payment.objects.filter(
      purchase_order=po, kind=Payment.Kind.ADVANCE, status=Payment.Status.PAID
    ).first()
    if payment is not None:
      refund = OwnerRefund.objects.create(
        payment=payment, invoice=invoice, source=OwnerRefund.Source.HELD,
        amount=held_by_kosh,
      )
      _enqueue_refund(refund)
  return debt


def _mode_for(account, amount_paise):
  if account.method == SupplierPayoutAccount.Method.UPI:
    if amount_paise > UPI_LIMIT_PAISE:
      raise PayoutError(
        "UPI payouts are limited to ₹1,00,000. Add a bank account to receive this amount.",
        "UPI_LIMIT_EXCEEDED",
      )
    return "UPI"
  return "IMPS" if amount_paise <= IMPS_LIMIT_PAISE else "NEFT"


def _narration(po):
  return re.sub(r"[^A-Za-z0-9 ]", " ", f"Kosh {po.number}")[:30]


@transaction.atomic
def send_payout(payout_id):
  payout = (
    Payout.objects.select_for_update(of=("self",))
    .select_related("purchase_order", "supplier_profile")
    .get(pk=payout_id)
  )
  if payout.status != Payout.Status.PENDING:
    return payout

  account = SupplierPayoutAccount.objects.filter(
    supplier_profile_id=payout.supplier_profile_id
  ).first()
  if account is None:
    payout.status = Payout.Status.ON_HOLD
    payout.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: events.payout_on_hold(payout))
    return payout

  amount = to_paise(payout.amount)
  try:
    mode = _mode_for(account, amount)
    result = _call(
      "POST", "/payouts",
      {
        "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER,
        "fund_account_id": account.razorpay_fund_account_id,
        "amount": amount,
        "currency": "INR",
        "mode": mode,
        "purpose": "vendor bill",
        "queue_if_low_balance": True,
        "reference_id": str(payout.pk),
        "narration": _narration(payout.purchase_order),
        "notes": {
          "purchase_order": payout.purchase_order.number,
          "invoice_id": str(payout.invoice_id),
        },
      },
      headers={"X-Payout-Idempotency": str(payout.idempotency_key)},
    )
  except PayoutError as err:
    if err.retryable:
      raise
    payout.status = Payout.Status.FAILED
    payout.failure_reason = err.message[:255]
    payout.attempts += 1
    payout.save(update_fields=["status", "failure_reason", "attempts", "updated_at"])
    transaction.on_commit(lambda: events.payout_failed(payout))
    return payout

  payout.razorpay_payout_id = result["id"]
  payout.mode = mode
  payout.fund_account_id = account.razorpay_fund_account_id
  payout.attempts += 1
  payout.sent_at = payout.sent_at or timezone.now()
  payout.status = Payout.Status.PROCESSING
  payout.save(update_fields=[
    "razorpay_payout_id", "mode", "fund_account_id", "attempts", "sent_at",
    "status", "updated_at",
  ])
  _apply_status(payout, result)
  return payout



def _failure_text(entity):
  details = entity.get("status_details") or {}
  text = details.get("description") or entity.get("failure_reason") or "The payout failed."
  return str(text)[:255]


def _treat_reversal_as_success():
  key = getattr(settings, "RAZORPAYX_KEY_ID", "") or settings.RAZORPAY_KEY_ID
  return bool(getattr(settings, "RAZORPAYX_TEST_REVERSAL_AS_SUCCESS", False)) and key.startswith("rzp_test_")

def _apply_status(payout, entity):
  raw_status = entity.get("status") or ""
  rz_status = raw_status
  if rz_status in FAILED_STATES and _treat_reversal_as_success():
    rz_status = "processed"
  if payout.status == Payout.Status.FAILED:
    return
  if payout.status == Payout.Status.PROCESSED and rz_status not in FAILED_STATES:
    return

  changed = ["razorpay_status", "updated_at"]
  payout.razorpay_status = raw_status
  if entity.get("utr"):
    payout.utr = entity["utr"]
    changed.append("utr")

  if rz_status == "processed":
    payout.status = Payout.Status.PROCESSED
    payout.processed_at = timezone.now()
    changed += ["status", "processed_at"]
    transaction.on_commit(lambda: events.payout_sent(payout))
  elif rz_status in FAILED_STATES:
    payout.status = Payout.Status.FAILED
    payout.failure_reason = _failure_text(entity)
    changed += ["status", "failure_reason"]
    transaction.on_commit(lambda: events.payout_failed(payout))
  elif rz_status in IN_FLIGHT:
    payout.status = Payout.Status.PROCESSING
    changed.append("status")
  payout.save(update_fields=changed)


def _find_payout(entity):
  qs = Payout.objects.select_for_update(of=("self",)).select_related(
    "purchase_order", "supplier_profile"
  )
  payout = qs.filter(razorpay_payout_id=entity.get("id")).first() if entity.get("id") else None
  if payout is None and entity.get("reference_id"):
    try:
      payout = qs.filter(pk=uuid.UUID(str(entity["reference_id"]))).first()
    except ValueError:
      payout = None
  return payout


def handle_payout_webhook(raw_body, signature):
  secret = getattr(settings, "RAZORPAYX_WEBHOOK_SECRET", "")
  if not secret or not signature:
    raise PayoutWebhookError("Missing signature.")
  expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
  if not hmac.compare_digest(expected, signature):
    raise PayoutWebhookError("Bad signature.")

  event = json.loads(raw_body)
  name = event.get("event") or ""
  if not name.startswith("payout.") or name.startswith("payout.downtime"):
    return "ignored"
  entity = (event.get("payload") or {}).get("payout", {}).get("entity") or {}

  with transaction.atomic():
    payout = _find_payout(entity)
    if payout is None:
      return "ignored"
    if not payout.razorpay_payout_id and entity.get("id"):
      payout.razorpay_payout_id = entity["id"]
      payout.save(update_fields=["razorpay_payout_id", "updated_at"])
    _apply_status(payout, entity)
  return name


@transaction.atomic
def sync_payout(payout_id):
  payout = (
    Payout.objects.select_for_update(of=("self",))
    .select_related("purchase_order", "supplier_profile")
    .get(pk=payout_id)
  )
  if payout.status != Payout.Status.PROCESSING or not payout.razorpay_payout_id:
    return payout
  entity = _call("GET", f"/payouts/{payout.razorpay_payout_id}")
  _apply_status(payout, entity)
  return payout