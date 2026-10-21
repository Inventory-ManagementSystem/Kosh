from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from notifications import events
from suppliers.models import SupplierProfile

from .models import Invoice, InvoiceItem, PurchaseOrder, Shipment, ShipmentItem
from .po_services import PurchaseOrderError
from .payout_services import create_advance_payout 

CENT = Decimal("0.01")


def next_invoice_number(supplier):
  numbers = Invoice.objects.filter(
    supplier_profile=supplier, number__regex=r"^INV-[0-9]+$"
  ).values_list("number", flat=True)
  highest = max((int(n.split("-")[1]) for n in numbers), default=0)
  return f"INV-{highest + 1:04d}"


def _money(value):
  return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _resolve_quantities(items, quantities):
  if quantities is None:
    return {item.id: item.quantity for item in items}

  by_id = {item.id: item for item in items}
  sent = {item.id: 0 for item in items}
  for item_id, qty in quantities.items():
    item = by_id.get(item_id)
    if item is None:
      raise PurchaseOrderError(
        "One of the items is not part of this order.", "INVALID_ITEM"
      )
    if qty > item.quantity:
      raise PurchaseOrderError(
        f"You can't dispatch more than ordered: {item.quantity} units of "
        f"{item.product_name}.",
        "QUANTITY_TOO_HIGH",
      )
    sent[item_id] = qty
  if not any(sent.values()):
    raise PurchaseOrderError("Dispatch at least one item.", "NOTHING_TO_DISPATCH")
  return sent


def _line_amounts(item, qty):
  if qty == item.quantity:
    return item.line_subtotal, item.line_tax, item.line_total
  subtotal = _money(item.unit_price * qty)
  tax = _money(subtotal * item.gst_rate / 100)
  return subtotal, tax, subtotal + tax


@transaction.atomic
def mark_dispatched(
  supplier, po_id, user, quantities=None, expected_delivery_date=None, tracking_note=""
):
  po = PurchaseOrder.objects.select_for_update().filter(
    pk=po_id, supplier_profile=supplier, status__in=PurchaseOrder.SUPPLIER_VISIBLE
  ).first()
  if po is None:
    raise PurchaseOrderError("Order not found.", "ORDER_NOT_FOUND")
  if po.status != PurchaseOrder.Status.ISSUED:
    raise PurchaseOrderError(
      "This order has already been dispatched.", "ALREADY_DISPATCHED"
    )
  SupplierProfile.objects.select_for_update().get(pk=supplier.pk)

  now = timezone.now()
  today = timezone.localdate()
  if expected_delivery_date is not None and expected_delivery_date < today:
    raise PurchaseOrderError(
      "The expected delivery date can't be in the past.", "EXPECTED_DATE_IN_PAST"
    )

  items = list(po.items.all())
  sent = _resolve_quantities(items, quantities)

  shipment = Shipment.objects.create(
    purchase_order=po,
    dispatched_at=now,
    expected_delivery_date=expected_delivery_date or po.delivery_date,
    tracking_note=tracking_note,
    created_by=user,
  )
  ShipmentItem.objects.bulk_create([
    ShipmentItem(shipment=shipment, purchase_order_item=item, quantity=sent[item.id])
    for item in items if sent[item.id] > 0
  ])

  lines = []
  for item in items:
    qty = sent[item.id]
    if qty > 0:
      lines.append((item, qty, *_line_amounts(item, qty)))

  subtotal = sum((line[2] for line in lines), Decimal("0"))
  tax_total = sum((line[3] for line in lines), Decimal("0"))
  grand_total = subtotal + tax_total
  advance_applied = min(po.advance_amount, grand_total)

  invoice = Invoice.objects.create(
    supplier_profile=supplier,
    business=po.business,
    purchase_order=po,
    number=next_invoice_number(supplier),
    issue_date=today,
    subtotal=subtotal,
    tax_total=tax_total,
    grand_total=grand_total,
    advance_applied=advance_applied,
    balance_due=grand_total - advance_applied,
  )
  InvoiceItem.objects.bulk_create([
    InvoiceItem(
      invoice=invoice,
      product_id=item.product_id,
      product_name=item.product_name,
      sku=item.sku,
      quantity=qty,
      unit_price=item.unit_price,
      gst_rate=item.gst_rate,
      line_subtotal=line_subtotal,
      line_tax=line_tax,
      line_total=line_total,
    )
    for item, qty, line_subtotal, line_tax, line_total in lines
  ])

  po.status = PurchaseOrder.Status.DISPATCHED
  po.save(update_fields=["status", "updated_at"])
  create_advance_payout(po, invoice)

  transaction.on_commit(lambda: events.goods_dispatched(po, shipment, invoice))
  return shipment, invoice
