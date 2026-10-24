import hashlib
import hmac
import json
import logging
from decimal import Decimal

import razorpay
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from notifications import events

from .models import RFQ, Invoice, OwnerRefund, Payment, PurchaseOrder, Quotation
from .po_services import PurchaseOrderError, confirm_order

logger = logging.getLogger(__name__)

GATEWAY_ERRORS = (
  razorpay.errors.BadRequestError,
  razorpay.errors.ServerError,
  razorpay.errors.GatewayError,
  requests.RequestException,
)


class PaymentError(PurchaseOrderError):
  pass


class WebhookError(Exception):
  pass


def to_paise(amount):
  return int((Decimal(amount) * 100).quantize(Decimal("1")))


def _client():
  key_id, key_secret = settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET
  if not (key_id and key_secret):
    raise PaymentError("Online payments aren't set up yet.", "PAYMENTS_NOT_CONFIGURED")
  client = razorpay.Client(auth=(key_id, key_secret))
  client.set_app_details({"title": "Kosh", "version": "1.0"})
  return client


def _gateway(call):
  try:
    return call(_client())
  except PaymentError:
    raise
  except GATEWAY_ERRORS as err:
    logger.warning("Razorpay call failed: %s", err)
    raise PaymentError(
      "Couldn't reach the payment gateway. Try again in a minute.", "GATEWAY_ERROR"
    ) from err


def _ensure_payable(po):
  if po.advance_amount <= 0:
    raise PaymentError("This order has no advance to pay.", "NO_ADVANCE_DUE")
  if po.status == PurchaseOrder.Status.CANCELLED:
    raise PaymentError("This order was cancelled.", "ORDER_CANCELLED")
  if po.status != PurchaseOrder.Status.AWAITING_ADVANCE:
    raise PaymentError("The advance for this order is already paid.", "ADVANCE_ALREADY_PAID")
  if po.advance_due_by and po.advance_due_by <= timezone.now():
    raise PaymentError("The time to pay this advance has run out.", "ADVANCE_EXPIRED")



@transaction.atomic
def start_advance_payment(business, po_id):
  po = (
    PurchaseOrder.objects.select_for_update(of=("self",))
    .select_related("business", "supplier_profile")
    .filter(pk=po_id, business=business)
    .first()
  )
  if po is None:
    raise PaymentError("Purchase order not found.", "ORDER_NOT_FOUND")
  _ensure_payable(po)

  payment = po.payments.filter(
    kind=Payment.Kind.ADVANCE, status=Payment.Status.CREATED, amount=po.advance_amount
  ).first()
  if payment:
    return po, payment

  order = _gateway(lambda c: c.order.create({
    "amount": to_paise(po.advance_amount),
    "currency": "INR",
    "receipt": f"{po.number}-ADV",
    "notes": {
      "purpose": "po_advance",
      "purchase_order_id": str(po.pk),
      "business_id": str(po.business_id),
    },
  }))
  payment = Payment.objects.create(
    purchase_order=po,
    amount=po.advance_amount,
    razorpay_order_id=order["id"],
  )
  return po, payment



def _verify(payments, order_id, payment_id, signature):
  client = _client()
  try:
    client.utility.verify_payment_signature({
      "razorpay_order_id": order_id,
      "razorpay_payment_id": payment_id,
      "razorpay_signature": signature,
    })
  except razorpay.errors.SignatureVerificationError as err:
    raise PaymentError("We couldn't verify this payment.", "INVALID_SIGNATURE") from err

  if not payments.filter(razorpay_order_id=order_id).exists():
    raise PaymentError("Payment not found.", "PAYMENT_NOT_FOUND")

  gateway_payment = _gateway(lambda c: c.payment.fetch(payment_id))
  return record_captured_payment(order_id, gateway_payment)


def verify_advance_payment(business, po_id, order_id, payment_id, signature):
  payments = Payment.objects.filter(
    kind=Payment.Kind.ADVANCE, purchase_order_id=po_id, purchase_order__business=business
  )
  return _verify(payments, order_id, payment_id, signature)


def record_captured_payment(order_id, gateway_payment):
  if gateway_payment.get("order_id") != order_id:
    raise PaymentError("This payment belongs to a different order.", "ORDER_MISMATCH")

  if gateway_payment.get("status") == "authorized":
    gateway_payment = _gateway(
      lambda c: c.payment.capture(
        gateway_payment["id"], gateway_payment["amount"], {"currency": "INR"}
      )
    )
  if gateway_payment.get("status") != "captured":
    raise PaymentError("This payment isn't complete yet.", "PAYMENT_NOT_CAPTURED")

  return _apply_capture(order_id, gateway_payment["id"], int(gateway_payment["amount"]))


@transaction.atomic
def _apply_capture(order_id, payment_id, amount_paise):
  payment = Payment.objects.select_for_update().filter(razorpay_order_id=order_id).first()
  if payment is None:
    raise PaymentError("Payment not found.", "PAYMENT_NOT_FOUND")

  po = PurchaseOrder.objects.select_for_update(of=("self",)).get(pk=payment.purchase_order_id)

  if payment.status in (Payment.Status.PAID, Payment.Status.REFUNDED):
    return po 

  if amount_paise != to_paise(payment.amount):
    logger.error("Amount mismatch on %s: got %s paise", order_id, amount_paise)
    raise PaymentError("The paid amount doesn't match the advance.", "AMOUNT_MISMATCH")

  payment.razorpay_payment_id = payment_id
  if payment.kind == Payment.Kind.BALANCE:
    return _apply_balance_capture(payment, po)

  if po.status != PurchaseOrder.Status.AWAITING_ADVANCE:
    payment.status = Payment.Status.REFUNDED
    payment.failure_reason = "Payment arrived after the order was closed; refunding."
    payment.save(update_fields=["status", "razorpay_payment_id", "failure_reason", "updated_at"])
    from .tasks import refund_advance_payment
    transaction.on_commit(lambda: refund_advance_payment.delay(str(payment.pk)))
    return po

  payment.status = Payment.Status.PAID
  payment.paid_at = timezone.now()
  payment.failure_reason = ""
  payment.save(update_fields=[
    "status", "razorpay_payment_id", "paid_at", "failure_reason", "updated_at"
  ])
  po = confirm_order(po) 
  transaction.on_commit(lambda: events.advance_paid(po))
  return po


def _refund_whole(payment, reason):
  payment.status = Payment.Status.REFUNDED
  payment.failure_reason = reason
  payment.save(update_fields=["status", "razorpay_payment_id", "failure_reason", "updated_at"])
  from .tasks import refund_advance_payment
  payment_pk = str(payment.pk)
  transaction.on_commit(lambda: refund_advance_payment.delay(payment_pk))


def _apply_balance_capture(payment, po):
  invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
  if invoice.status == Invoice.Status.PAID or invoice.balance_due != payment.amount:
    _refund_whole(payment, "The invoice was already settled; refunding.")
    return po

  payment.status = Payment.Status.PAID
  payment.paid_at = timezone.now()
  payment.failure_reason = ""
  payment.save(update_fields=[
    "status", "razorpay_payment_id", "paid_at", "failure_reason", "updated_at"
  ])
  invoice.status = Invoice.Status.PAID
  invoice.save(update_fields=["status", "updated_at"])

  from .payout_services import create_balance_payout
  create_balance_payout(po, invoice)
  transaction.on_commit(lambda: events.balance_paid(po, invoice))
  return po


def record_payment_failure(order_id, gateway_payment):
  reason = (gateway_payment.get("error_description") or "Payment failed.")[:255]
  Payment.objects.filter(
    razorpay_order_id=order_id, status=Payment.Status.CREATED
  ).update(failure_reason=reason, updated_at=timezone.now())


def handle_webhook(raw_body, signature):
  secret = settings.RAZORPAY_WEBHOOK_SECRET
  if not secret or not signature:
    raise WebhookError("Missing signature.")
  expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
  if not hmac.compare_digest(expected, signature):
    raise WebhookError("Bad signature.")

  event = json.loads(raw_body)
  name = event.get("event")
  entity = event.get("payload", {}).get("payment", {}).get("entity") or {}
  order_id = entity.get("order_id")

  if not order_id or not Payment.objects.filter(razorpay_order_id=order_id).exists():
    return "ignored" 

  if name in ("order.paid", "payment.captured"):
    record_captured_payment(order_id, entity)
  elif name == "payment.failed":
    record_payment_failure(order_id, entity)
  return name



def _captured_on_gateway(order_id):
  result = _gateway(lambda c: c.order.payments(order_id))
  for item in result.get("items", []):
    if item.get("status") in ("captured", "authorized"):
      return item
  return None


def expire_advance(po_id): 
  open_payments = Payment.objects.filter(
    kind=Payment.Kind.ADVANCE,
    purchase_order_id=po_id,
    status=Payment.Status.CREATED,
  ).values_list("razorpay_order_id", flat=True)
  for order_id in list(open_payments):
    captured = _captured_on_gateway(order_id)
    if captured:
      record_captured_payment(order_id, captured)
      return False
  return _cancel_unpaid(po_id)


@transaction.atomic
def _cancel_unpaid(po_id):
  now = timezone.now()
  po = PurchaseOrder.objects.select_for_update(of=("self",)).get(pk=po_id)
  if po.status != PurchaseOrder.Status.AWAITING_ADVANCE:
    return False
  if po.advance_due_by and po.advance_due_by > now:
    return False

  po.status = PurchaseOrder.Status.CANCELLED
  po.cancelled_at = now
  po.save(update_fields=["status", "cancelled_at", "updated_at"])

  po.payments.filter(status=Payment.Status.CREATED).update(
    status=Payment.Status.FAILED,
    failure_reason="Advance not paid in time.",
    updated_at=now,
  )

  rfq = RFQ.objects.select_for_update().get(pk=po.rfq_id)
  if rfq.status == RFQ.Status.AWARDED:
    rfq.status = RFQ.Status.OPEN if rfq.deadline > now else RFQ.Status.CLOSED
    rfq.save(update_fields=["status", "updated_at"])
  Quotation.objects.filter(pk=po.quotation_id, status=Quotation.Status.ACCEPTED).update(
    status=Quotation.Status.SUBMITTED, updated_at=now
  )

  transaction.on_commit(lambda: events.advance_expired(po))
  return True


def refund_payment(payment_pk):
  payment = Payment.objects.select_related("purchase_order").get(pk=payment_pk)
  if payment.refund_id or not payment.razorpay_payment_id:
    return payment.refund_id
  refund = _gateway(lambda c: c.payment.refund(payment.razorpay_payment_id, {
    "amount": to_paise(payment.amount),
    "notes": {"reason": "po_closed", "purchase_order_id": str(payment.purchase_order_id)},
  }))
  Payment.objects.filter(pk=payment.pk).update(refund_id=refund["id"], updated_at=timezone.now())
  events.advance_refunded(payment.purchase_order, payment.amount)
  return refund["id"]


def _ensure_balance_payable(invoice):
  po = invoice.purchase_order
  if po.status not in (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.PARTIALLY_RECEIVED):
    raise PaymentError(
      "Confirm the goods receipt before paying the balance.", "GOODS_NOT_RECEIVED"
    )
  if invoice.status == Invoice.Status.PAID:
    raise PaymentError("This invoice is already paid.", "INVOICE_ALREADY_PAID")
  if invoice.balance_due <= 0:
    raise PaymentError("Nothing is left to pay on this invoice.", "NO_BALANCE_DUE")


@transaction.atomic
def start_balance_payment(business, invoice_id):
  invoice = (
    Invoice.objects.select_for_update(of=("self",))
    .select_related("purchase_order", "supplier_profile")
    .filter(pk=invoice_id, business=business)
    .first()
  )
  if invoice is None:
    raise PaymentError("Invoice not found.", "INVOICE_NOT_FOUND")
  _ensure_balance_payable(invoice)

  payment = Payment.objects.filter(
    invoice=invoice, kind=Payment.Kind.BALANCE,
    status=Payment.Status.CREATED, amount=invoice.balance_due,
  ).first()
  if payment:
    return invoice, payment

  po = invoice.purchase_order
  order = _gateway(lambda c: c.order.create({
    "amount": to_paise(invoice.balance_due),
    "currency": "INR",
    "receipt": f"{invoice.number}-BAL"[:40],
    "notes": {
      "purpose": "invoice_balance",
      "purchase_order_id": str(po.pk),
      "invoice_id": str(invoice.pk),
      "business_id": str(business.pk),
    },
  }))
  payment = Payment.objects.create(
    purchase_order=po,
    invoice=invoice,
    kind=Payment.Kind.BALANCE,
    amount=invoice.balance_due,
    razorpay_order_id=order["id"],
  )
  return invoice, payment


def verify_balance_payment(business, invoice_id, order_id, payment_id, signature):
  payments = Payment.objects.filter(
    kind=Payment.Kind.BALANCE, invoice_id=invoice_id, invoice__business=business
  )
  return _verify(payments, order_id, payment_id, signature)



def send_owner_refund(refund_pk):
  with transaction.atomic():
    refund = (
      OwnerRefund.objects.select_for_update(of=("self",))
      .select_related("payment", "invoice")
      .get(pk=refund_pk)
    )
    if refund.status != OwnerRefund.Status.PENDING:
      return refund
    try:
      result = _gateway(lambda c: c.payment.refund(refund.payment.razorpay_payment_id, {
        "amount": to_paise(refund.amount),
        "notes": {"reason": f"goods_receipt_{refund.source}", "invoice": refund.invoice.number},
        "receipt": f"{str(refund.pk)[:32]}",
      }))
    except PaymentError as err:
      if err.code in ("GATEWAY_ERROR", "PAYMENTS_NOT_CONFIGURED"):
        raise 
      refund.status = OwnerRefund.Status.FAILED
      refund.failure_reason = err.message[:255]
      refund.save(update_fields=["status", "failure_reason", "updated_at"])
      return refund
    refund.status = OwnerRefund.Status.PROCESSED
    refund.razorpay_refund_id = result.get("id", "")
    refund.save(update_fields=["status", "razorpay_refund_id", "updated_at"])
  events.owner_refund_sent(refund)
  return refund
