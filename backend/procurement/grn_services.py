from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.models import Business
from inventory.ledger import record_movement
from inventory.models import StockMovement
from notifications import events

from .alert_services import check_low_stock_on_commit
from .dispatch_services import _line_amounts
from .models import (
  GoodsReceipt,
  GoodsReceiptDiscrepancy,
  GoodsReceiptItem,
  Invoice,
  PurchaseOrder,
  ReorderSuggestion,
)
from .payout_services import settle_after_receipt
from .po_services import PurchaseOrderError

Kind = GoodsReceiptDiscrepancy.Kind


def next_grn_number(business):
  numbers = GoodsReceipt.objects.filter(
    business=business, number__regex=r"^GRN-[0-9]+$"
  ).values_list("number", flat=True)
  highest = max((int(n.split("-")[1]) for n in numbers), default=0)
  return f"GRN-{highest + 1:04d}"


def _read_lines(items, shipped, lines):
  by_id = {item.id: item for item in items}
  entered = {}
  for line in lines:
    item_id = line["purchase_order_item"]
    item = by_id.get(item_id)
    if item is None:
      raise PurchaseOrderError(
        "One of the items is not part of this order.", "INVALID_ITEM"
      )
    if item_id in entered:
      raise PurchaseOrderError("Each item can appear only once.", "DUPLICATE_ITEM")
    received = line["received_quantity"]
    rejected = line.get("rejected_quantity", 0)
    if rejected > received:
      raise PurchaseOrderError(
        f"Rejected can't be more than received for {item.product_name}.",
        "REJECTED_TOO_HIGH",
      )
    entered[item_id] = {
      "received": received, "rejected": rejected, "note": line.get("note", ""),
    }

  missing = [
    item.product_name for item in items
    if shipped.get(item.id, 0) > 0 and item.id not in entered
  ]
  if missing:
    raise PurchaseOrderError(
      "Enter the received quantity for every dispatched item: "
      + ", ".join(missing) + ".",
      "MISSING_ITEMS",
    )
  return entered


@transaction.atomic
def receive_goods(business, po_id, user, lines, notes=""):
  po = PurchaseOrder.objects.select_for_update().filter(
    pk=po_id, business=business
  ).first()
  if po is None:
    raise PurchaseOrderError("Order not found.", "ORDER_NOT_FOUND")
  if po.status in (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.PARTIALLY_RECEIVED):
    raise PurchaseOrderError(
      "Goods for this order were already received.", "ALREADY_RECEIVED"
    )
  if po.status != PurchaseOrder.Status.DISPATCHED:
    raise PurchaseOrderError(
      "This order hasn't been dispatched yet.", "ORDER_NOT_DISPATCHED"
    )
  Business.objects.select_for_update().get(pk=business.pk)

  items = list(po.items.all())
  shipped = {s.purchase_order_item_id: s.quantity for s in po.shipment.items.all()}
  entered = _read_lines(items, shipped, lines)
  if not any(line["received"] for line in entered.values()):
    raise PurchaseOrderError(
      "Nothing was received. If the delivery hasn't arrived, don't confirm it yet.",
      "NOTHING_RECEIVED",
    )

  invoice = Invoice.objects.select_for_update().get(purchase_order=po)
  invoice_items = {i.product_id: i for i in invoice.items.all()}

  grn = GoodsReceipt.objects.create(
    business=business,
    purchase_order=po,
    number=next_grn_number(business),
    notes=notes,
    received_by=user,
  )

  credit_total = Decimal("0")
  stock_in = []
  for item in items:
    line = entered.get(item.id, {})
    dispatched = shipped.get(item.id, 0)
    received = line.get("received", 0)
    rejected = line.get("rejected", 0)
    accepted = received - rejected

    credit = Decimal("0")
    invoice_item = invoice_items.get(item.product_id)
    if invoice_item is not None:
      billable = min(accepted, dispatched)
      credit = invoice_item.line_total - _line_amounts(invoice_item, billable)[2]
    credit_total += credit

    receipt_item = GoodsReceiptItem.objects.create(
      goods_receipt=grn,
      purchase_order_item=item,
      ordered_quantity=item.quantity,
      dispatched_quantity=dispatched,
      received_quantity=received,
      rejected_quantity=rejected,
      credit_amount=credit,
      note=line.get("note", ""),
    )
    GoodsReceiptDiscrepancy.objects.bulk_create([
      GoodsReceiptDiscrepancy(
        goods_receipt=grn, receipt_item=receipt_item, kind=kind, quantity=qty
      )
      for kind, qty in (
        (Kind.SHORT_SHIPPED, item.quantity - dispatched),
        (Kind.SHORT_RECEIVED, dispatched - received),
        (Kind.REJECTED, rejected),
        (Kind.EXCESS, received - dispatched),
      )
      if qty > 0
    ])
    if accepted > 0:
      stock_in.append((item.product_id, accepted))

  for product_id, accepted in sorted(stock_in, key=lambda row: str(row[0])):
    record_movement(
      business=business,
      product_id=product_id,
      change=accepted,
      reason=StockMovement.Reason.GRN_RECEIVED,
      user=user,
      note=f"{grn.number} / {po.number}",
    )

  payable = invoice.grand_total - credit_total
  applied = min(po.advance_amount, payable)
  invoice.discrepancy_credit = credit_total
  invoice.advance_applied = applied
  invoice.balance_due = payable - applied
  invoice.refund_due = po.advance_amount - applied
  invoice.save(update_fields=[
    "discrepancy_credit", "advance_applied", "balance_due", "refund_due", "updated_at"
  ])
  settle_after_receipt(po, invoice)

  po.status = PurchaseOrder.Status.RECEIVED
  po.save(update_fields=["status", "updated_at"])

  ReorderSuggestion.objects.filter(
    rfq_id=po.rfq_id, status=ReorderSuggestion.Status.RFQ_CREATED
  ).update(status=ReorderSuggestion.Status.CLOSED, updated_at=timezone.now())

  check_low_stock_on_commit(business, [item.product_id for item in items])
  transaction.on_commit(lambda: events.goods_received(po, grn, invoice))
  return grn, invoice
