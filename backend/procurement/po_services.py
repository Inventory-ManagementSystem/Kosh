from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Business
from notifications import events

from .models import(
    RFQ,
    Payment,
    PurchaseOrder, 
    PurchaseOrderItem, 
    Quotation, 
    RFQRecipient,
)


class PurchaseOrderError(Exception):
  def __init__(self, message, code):
    super().__init__(message)
    self.message = message
    self.code = code


def next_po_number(business):
  numbers = PurchaseOrder.objects.filter(
    business=business, number__regex=r"^PO-[0-9]+$"
  ).values_list("number", flat=True)
  highest = max((int(n.split("-")[1]) for n in numbers), default=0)
  return f"PO-{highest + 1:04d}"


def _ensure_acceptable(rfq, quotation):
  if rfq.status == RFQ.Status.CANCELLED:
    raise PurchaseOrderError("This RFQ was cancelled.", "RFQ_CANCELLED")
  if rfq.status == RFQ.Status.AWARDED:
    raise PurchaseOrderError(
      "A quotation has already been accepted for this RFQ.", "RFQ_ALREADY_AWARDED"
    )
  if quotation.status != Quotation.Status.SUBMITTED:
    raise PurchaseOrderError("This quotation is no longer active.", "QUOTATION_NOT_ACTIVE")
  if quotation.valid_until < timezone.localdate():
    raise PurchaseOrderError(
      f"This quotation expired on {quotation.valid_until:%d %b %Y}.", "QUOTATION_EXPIRED"
    )

  wanted = {item.id: item.quantity for item in rfq.items.all()}
  quoted = {line.rfq_item_id: line.quantity for line in quotation.items.all()}
  if wanted != quoted:
    raise PurchaseOrderError(
      "This quotation doesn't cover every item at the full quantity.",
      "QUOTATION_INCOMPLETE",
    )


@transaction.atomic
def accept_quotation(business, quotation_id):
  quotation = Quotation.objects.filter(pk=quotation_id, rfq__business=business).first()
  if quotation is None:
    raise PurchaseOrderError("Quotation not found.", "QUOTATION_NOT_FOUND")

  RFQRecipient.objects.select_for_update().get(pk=quotation.recipient_id)
  rfq = RFQ.objects.select_for_update().get(pk=quotation.rfq_id)
  Business.objects.select_for_update().get(pk=business.pk)

  quotation = (
    Quotation.objects.select_related("supplier_profile")
    .prefetch_related("items__rfq_item")
    .get(pk=quotation.pk)
  )
  _ensure_acceptable(rfq, quotation)

  now = timezone.now()
  advance = quotation.advance_amount
  po = PurchaseOrder.objects.create(
    business=business,
    number=next_po_number(business),
    rfq=rfq,
    quotation=quotation,
    supplier_profile=quotation.supplier_profile,
    subtotal=quotation.subtotal,
    tax_total=quotation.tax_total,
    grand_total=quotation.grand_total,
    advance_amount=advance,
    delivery_date=quotation.delivery_date,
    advance_due_by=(
      now + timedelta(hours=settings.PO_ADVANCE_EXPIRY_HOURS) if advance > 0 else None
    ),
  )
  PurchaseOrderItem.objects.bulk_create([
    PurchaseOrderItem(
      purchase_order=po,
      product_id=line.rfq_item.product_id,
      product_name=line.rfq_item.product_name,
      sku=line.rfq_item.sku,
      quantity=line.quantity,
      unit_price=line.unit_price,
      gst_rate=line.gst_rate,
      line_subtotal=line.line_subtotal,
      line_tax=line.line_tax,
      line_total=line.line_total,
    )
    for line in quotation.items.all()
  ])

  quotation.status = Quotation.Status.ACCEPTED
  quotation.save(update_fields=["status", "updated_at"])
  rfq.status = RFQ.Status.AWARDED
  rfq.save(update_fields=["status", "updated_at"])

  if advance <= 0:
    po = confirm_order(po)
  return po


def _announce_confirmed(po, rejected):
  events.purchase_order_issued(po)
  if rejected:
    events.quotations_rejected(po.rfq, rejected)
  events.rfq_awarded(po.rfq)


@transaction.atomic
def confirm_order(po):
  po = (
    PurchaseOrder.objects.select_for_update(of=("self",))
    .select_related(
      "business", "supplier_profile__user", "rfq__business", "rfq__supply_category"
    )
    .get(pk=po.pk)
  )
  if po.status == PurchaseOrder.Status.CANCELLED:
    raise PurchaseOrderError(
      "This order was cancelled, so it can't be confirmed.", "ORDER_CANCELLED"
    )
  if po.status != PurchaseOrder.Status.AWAITING_ADVANCE:
    return po

  now = timezone.now()
  po.status = PurchaseOrder.Status.ISSUED
  po.issued_at = now
  po.save(update_fields=["status", "issued_at", "updated_at"])

  rejected = list(
    Quotation.objects.filter(rfq_id=po.rfq_id, status=Quotation.Status.SUBMITTED)
    .exclude(pk=po.quotation_id)
    .select_related("supplier_profile__user")
  )
  if rejected:
    Quotation.objects.filter(pk__in=[q.pk for q in rejected]).update(
      status=Quotation.Status.REJECTED, updated_at=now
    )

  transaction.on_commit(lambda: _announce_confirmed(po, rejected))
  return po

def _cancel_locked(po, now):
  rfq = RFQ.objects.select_for_update().get(pk=po.rfq_id)

  po.status = PurchaseOrder.Status.CANCELLED
  po.cancelled_at = now
  po.save(update_fields=["status", "cancelled_at", "updated_at"])

  Quotation.objects.filter(
    pk=po.quotation_id, status=Quotation.Status.ACCEPTED
  ).update(status=Quotation.Status.SUBMITTED, updated_at=now)

  if rfq.status == RFQ.Status.AWARDED:
    rfq.status = RFQ.Status.OPEN if rfq.deadline > now else RFQ.Status.CLOSED
    rfq.save(update_fields=["status", "updated_at"])
  return po


@transaction.atomic
def cancel_unpaid_order(business, po_id):
  po = PurchaseOrder.objects.select_for_update().filter(
    pk=po_id, business=business
  ).first()
  if po is None:
    raise PurchaseOrderError("Order not found.", "ORDER_NOT_FOUND")
  if po.status != PurchaseOrder.Status.AWAITING_ADVANCE:
    raise PurchaseOrderError(
      "Only an order that is waiting for its advance can be cancelled.",
      "ORDER_NOT_CANCELLABLE",
    )
  if po.payments.filter(status=Payment.Status.PAID).exists():
    raise PurchaseOrderError(
      "The advance has already been paid, so this order can't be cancelled here.",
      "PAYMENT_RECEIVED",
    )
  return _cancel_locked(po, timezone.now())
