from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify

from .models import RFQ, Quotation, QuotationItem, RFQRecipient

CENT = Decimal("0.01")

QUOTATION_VALIDITY_DAYS = 7


class QuotationError(Exception):
  def __init__(self, message, code):
    super().__init__(message)
    self.message = message
    self.code = code


def _money(value):
  return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_line(unit_price, quantity, gst_rate):
  line_subtotal = _money(unit_price * quantity)
  line_tax = _money(line_subtotal * gst_rate / 100)
  return line_subtotal, line_tax, line_subtotal + line_tax


def calculate_totals(items):
  subtotal = tax_total = Decimal("0")
  for line in items:
    line_subtotal, line_tax, _ = calculate_line(
      line["unit_price"], line["quantity"], line["gst_rate"]
    )
    subtotal += line_subtotal
    tax_total += line_tax
  return subtotal, tax_total, subtotal + tax_total


def default_valid_until(rfq):
  return timezone.localdate(rfq.deadline) + timedelta(days=QUOTATION_VALIDITY_DAYS)


def ensure_rfq_accepting(rfq):
  if rfq.status != RFQ.Status.OPEN:
    raise QuotationError("This RFQ is no longer accepting quotations.", "RFQ_NOT_OPEN")
  if rfq.deadline <= timezone.now():
    raise QuotationError("The deadline for this RFQ has passed.", "RFQ_DEADLINE_PASSED")


def _lock_recipient(recipient):
  return (
    RFQRecipient.objects.select_for_update()
    .select_related("rfq__business__owner", "supplier_profile")
    .get(pk=recipient.pk)
  )


def _notify_owner(rfq, title, body, push=True):
  notify(rfq.business.owner, title, body, kind=Notification.Kind.QUOTATION, push=push)


def mark_viewed(recipient):
  if recipient.status != RFQRecipient.Status.SENT:
    return recipient
  now = timezone.now()
  updated = RFQRecipient.objects.filter(
    pk=recipient.pk, status=RFQRecipient.Status.SENT
  ).update(status=RFQRecipient.Status.VIEWED, viewed_at=now)
  if updated:
    recipient.status = RFQRecipient.Status.VIEWED
    recipient.viewed_at = now
  return recipient


@transaction.atomic
def submit_quotation(recipient, data):
  recipient = _lock_recipient(recipient)
  rfq = recipient.rfq
  ensure_rfq_accepting(rfq)

  quotation = Quotation.objects.filter(recipient=recipient).first()
  created = quotation is None
  if created:
    quotation = Quotation(
      rfq=rfq, recipient=recipient, supplier_profile=recipient.supplier_profile
    )
  else:
    if quotation.status in Quotation.DECIDED:
      raise QuotationError("This quotation has already been decided.", "QUOTATION_DECIDED")
    quotation.revision += 1

  now = timezone.now()
  quotation.status = Quotation.Status.SUBMITTED
  quotation.delivery_date = data["delivery_date"]
  quotation.advance_amount = data.get("advance_amount", Decimal("0"))
  quotation.valid_until = data.get("valid_until") or default_valid_until(rfq)
  quotation.notes = data.get("notes", "")
  quotation.submitted_at = now

  lines = []
  for line in data["items"]:
    line_subtotal, line_tax, line_total = calculate_line(
      line["unit_price"], line["quantity"], line["gst_rate"]
    )
    lines.append(QuotationItem(
      rfq_item=line["rfq_item"],
      quantity=line["quantity"],
      unit_price=line["unit_price"],
      gst_rate=line["gst_rate"],
      line_subtotal=line_subtotal,
      line_tax=line_tax,
      line_total=line_total,
    ))

  quotation.subtotal, quotation.tax_total, quotation.grand_total = calculate_totals(data["items"])
  if quotation.advance_amount > quotation.grand_total:
    raise QuotationError("Advance payment cannot exceed the total amount.", "ADVANCE_TOO_HIGH")
  quotation.save()

  quotation.items.all().delete()
  for item in lines:
    item.quotation = quotation
  QuotationItem.objects.bulk_create(lines)

  recipient.status = RFQRecipient.Status.QUOTED
  recipient.viewed_at = recipient.viewed_at or now
  recipient.responded_at = now
  recipient.save(update_fields=["status", "viewed_at", "responded_at"])

  company = recipient.supplier_profile.company_name
  if created:
    title = f"New quotation for {rfq.number}"
  else:
    title = f"Quotation revised for {rfq.number}"
  _notify_owner(rfq, title, f"{company} quoted ₹{quotation.grand_total} (incl. GST).")

  return quotation, created


@transaction.atomic
def withdraw_quotation(recipient):
  recipient = _lock_recipient(recipient)
  rfq = recipient.rfq
  ensure_rfq_accepting(rfq)

  quotation = Quotation.objects.filter(
    recipient=recipient, status=Quotation.Status.SUBMITTED
  ).first()
  if quotation is None:
    raise QuotationError("You have no active quotation on this RFQ.", "NO_ACTIVE_QUOTATION")

  quotation.status = Quotation.Status.WITHDRAWN
  quotation.save(update_fields=["status", "updated_at"])

  recipient.status = RFQRecipient.Status.VIEWED
  recipient.responded_at = None
  recipient.save(update_fields=["status", "responded_at"])

  _notify_owner(
    rfq,
    f"Quotation withdrawn for {rfq.number}",
    f"{recipient.supplier_profile.company_name} withdrew their quotation.",
    push=False,
  )
  return quotation


@transaction.atomic
def decline_rfq(recipient):
  recipient = _lock_recipient(recipient)
  rfq = recipient.rfq
  ensure_rfq_accepting(rfq)

  if recipient.status == RFQRecipient.Status.DECLINED:
    raise QuotationError("You have already declined this RFQ.", "ALREADY_DECLINED")
  if Quotation.objects.filter(recipient=recipient, status=Quotation.Status.SUBMITTED).exists():
    raise QuotationError("Withdraw your quotation before declining.", "QUOTATION_ACTIVE")

  now = timezone.now()
  recipient.status = RFQRecipient.Status.DECLINED
  recipient.viewed_at = recipient.viewed_at or now
  recipient.responded_at = now
  recipient.save(update_fields=["status", "viewed_at", "responded_at"])

  _notify_owner(
    rfq,
    f"Supplier declined {rfq.number}",
    f"{recipient.supplier_profile.company_name} won't be quoting on this RFQ.",
    push=False,
  )
  return recipient
