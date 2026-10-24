import inspect
import json
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.models import Employee, EmployeeInvite
from accounts.utils import invite_cutoff
from customers.models import Customer
from inventory.models import Category, DispatchItem, DispatchNote, Product, StockMovement
from inventory.reorder import calculate_reorder, get_dispatch_stats
from procurement.models import (
  RFQ,
  GoodsReceipt,
  GoodsReceiptDiscrepancy,
  Invoice,
  OwnerRefund,
  Payment,
  Payout,
  PurchaseOrder,
  Quotation,
  ReorderSuggestion,
  SupplierDebt,
)
from suppliers.models import Supplier
from .knowledge import get_app_help

MAX_LIMIT = 25
MAX_DAYS = 365


class ToolError(Exception):
  """"""


def _limit(value, default=10):
  try:
    value = int(value)
  except (TypeError, ValueError):
    return default
  return max(1, min(value, MAX_LIMIT))


def _days(value, default=30):
  try:
    value = int(value)
  except (TypeError, ValueError):
    return default
  return max(1, min(value, MAX_DAYS))


def _money_sum(expression):
  return Coalesce(
    Sum(expression, output_field=DecimalField(max_digits=18, decimal_places=2)),
    0,
    output_field=DecimalField(max_digits=18, decimal_places=2),
  )


def _stock_status_filter(status):
  if status == "out_of_stock":
    return Q(quantity=0)
  if status == "low_stock":
    return Q(quantity__gt=0, quantity__lte=F("low_stock_threshold"))
  if status == "in_stock":
    return Q(quantity__gt=F("low_stock_threshold"))
  raise ToolError("stock_status must be one of: in_stock, low_stock, out_of_stock.")


def _find_product(business, product):
  product = (product or "").strip()
  if not product:
    raise ToolError("Give a product name or SKU.")
  products = Product.objects.filter(business=business).select_related("category")
  match = products.filter(sku__iexact=product).first()
  if match:
    return match
  matches = list(products.filter(name__icontains=product)[:6])
  if len(matches) == 1:
    return matches[0]
  if not matches:
    raise ToolError(f"No product found matching '{product}'.")
  options = ", ".join(f"{p.name} ({p.sku})" for p in matches[:5])
  raise ToolError(f"Several products match '{product}': {options}. Ask which one, or use the SKU.")


def _product_row(p):
  return {
    "name": p.name,
    "sku": p.sku,
    "category": p.category.name if p.category else None,
    "quantity": p.quantity,
    "low_stock_threshold": p.low_stock_threshold,
    "status": p.status,
    "price": p.price,
    "cost_price": p.cost_price,
    "is_active": p.is_active,
  }


def _has_field(model, name):
  try:
    model._meta.get_field(name)
    return True
  except FieldDoesNotExist:
    return False


def _rfq_category(rfq):
  category = getattr(rfq, "supply_category", None)
  return category.name if category else None


def _suggestion_rfq_number(suggestion):
  try:
    rfq = suggestion.rfq 
  except ObjectDoesNotExist:
    return None
  return rfq.number if rfq else None


def to_json_safe(data):
  return json.loads(json.dumps(data, cls=DjangoJSONEncoder))



def get_inventory_overview(business):
  products = Product.objects.filter(business=business, is_active=True)
  totals = products.aggregate(
    product_count=Count("id"),
    total_units=Coalesce(Sum("quantity"), 0),
    out_of_stock=Count("id", filter=Q(quantity=0)),
    low_stock=Count("id", filter=Q(quantity__gt=0, quantity__lte=F("low_stock_threshold"))),
    stock_value_at_selling_price=_money_sum(F("quantity") * F("price")),
    stock_value_at_cost=_money_sum(F("quantity") * F("cost_price")),
    products_without_cost_price=Count("id", filter=Q(cost_price__isnull=True)),
  )
  totals["category_count"] = Category.objects.filter(business=business).count()
  totals["inactive_products"] = Product.objects.filter(business=business, is_active=False).count()
  totals["open_reorder_alerts"] = ReorderSuggestion.objects.filter(
    business=business, status__in=ReorderSuggestion.ACTIVE
  ).count()
  return totals


def get_business_insights(business, days=30):
  days = _days(days)
  since = timezone.now() - timedelta(days=days)
  active = Product.objects.filter(business=business, is_active=True).select_related("category")

  needs_restock = [
    _product_row(p)
    for p in active.filter(quantity__lte=F("low_stock_threshold")).order_by("quantity", "name")[:10]
  ]

  dispatched_ids = set(
    StockMovement.objects.filter(
      business=business, reason=StockMovement.Reason.DISPATCH, created_at__gte=since
    ).values_list("product_id", flat=True)
  )
  slow_movers = active.filter(quantity__gt=0).exclude(id__in=dispatched_ids)
  slow_value = slow_movers.aggregate(value=_money_sum(F("quantity") * F("price")))["value"]

  open_rfqs = RFQ.objects.filter(business=business, status=RFQ.Status.OPEN)
  awaiting_quotes = (
    open_rfqs.annotate(
      quotes=Count("quotations", filter=~Q(quotations__status=Quotation.Status.WITHDRAWN))
    ).filter(quotes=0).count()
  )
  damaged_units = StockMovement.objects.filter(
    business=business, reason=StockMovement.Reason.DAMAGED, created_at__gte=since
  ).aggregate(units=Coalesce(Sum("quantity_change"), 0))["units"]

  dispatch = get_dispatch_summary(business, days=days)
  orders = PurchaseOrder.objects.filter(business=business)
  now = timezone.now()
  return {
    "period_days": days,
    "overview": get_inventory_overview(business),
    "products_needing_restock": needs_restock,
    "top_dispatched_products": dispatch["top_products"][:5],
    "dispatch_by_outlet": dispatch["by_outlet"],
    "units_dispatched": dispatch["total_units"],
    "slow_moving_products": {
      "count": slow_movers.count(),
      "stock_value_at_selling_price": slow_value,
      "examples": [
        {"name": p.name, "sku": p.sku, "quantity": p.quantity}
        for p in slow_movers.order_by("-quantity")[:5]
      ],
      "meaning": f"In stock but not dispatched in the last {days} days.",
    },
    "damaged_units": abs(damaged_units),
    "procurement": {
      "open_rfqs": open_rfqs.count(),
      "open_rfqs_without_any_quotation": awaiting_quotes,
      "open_reorder_alerts": ReorderSuggestion.objects.filter(
        business=business, status__in=ReorderSuggestion.ACTIVE
      ).count(),
    },
    "purchase_orders": {
      "awaiting_advance": orders.filter(status=PurchaseOrder.Status.AWAITING_ADVANCE).count(),
      "advance_due_within_24h": orders.filter(
        status=PurchaseOrder.Status.AWAITING_ADVANCE,
        advance_due_by__lte=now + timedelta(hours=24),
      ).count(),
      "waiting_for_supplier_dispatch": orders.filter(status=PurchaseOrder.Status.ISSUED).count(),
      "dispatched_not_received": orders.filter(status=PurchaseOrder.Status.DISPATCHED).count(),
      "late_shipments": orders.filter(
        status=PurchaseOrder.Status.DISPATCHED,
        shipment__expected_delivery_date__gt=F("delivery_date"),
      ).count(),
      "receipts_with_issues": GoodsReceipt.objects.filter(
        business=business, created_at__gte=since, discrepancies__isnull=False
      ).distinct().count(),
      "unpaid_invoice_balance": Invoice.objects.filter(
        business=business, status=Invoice.Status.UNPAID
      ).aggregate(total=_money_sum(F("balance_due")))["total"],
    },
    "supplier_payments": _supplier_payment_summary(business),
  }


RECEIVED_STATUSES = (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.PARTIALLY_RECEIVED)


def _payouts_needing_attention(business):
  payouts = Payout.objects.filter(purchase_order__business=business)
  active = set(
    payouts.filter(status__in=Payout.ACTIVE).values_list("purchase_order_id", "kind")
  )
  failed = {
    (po_id, kind)
    for po_id, kind in payouts.filter(status=Payout.Status.FAILED)
    .values_list("purchase_order_id", "kind")
    if (po_id, kind) not in active
  }
  return payouts.filter(status=Payout.Status.ON_HOLD).count(), len(failed)


def _supplier_payment_summary(business):
  unpaid = Invoice.objects.filter(business=business, status=Invoice.Status.UNPAID)
  ready = unpaid.filter(purchase_order__status__in=RECEIVED_STATUSES, balance_due__gt=0)
  on_hold, failed = _payouts_needing_attention(business)
  return {
    "invoices_ready_to_pay": ready.count(),
    "balance_ready_to_pay": ready.aggregate(total=_money_sum(F("balance_due")))["total"],
    "invoices_waiting_for_goods_receipt": unpaid.filter(
      purchase_order__status=PurchaseOrder.Status.DISPATCHED
    ).count(),
    "payouts_on_hold_for_supplier_bank_details": on_hold,
    "payouts_failed": failed,
    "refunds_to_owner_pending": OwnerRefund.objects.filter(
      invoice__business=business, status=OwnerRefund.Status.PENDING
    ).count(),
  }


def search_products(business, query="", stock_status=None, category=None,
                    include_inactive=False, limit=15):
  products = Product.objects.filter(business=business).select_related("category")
  if not include_inactive:
    products = products.filter(is_active=True)
  if query:
    products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
  if stock_status:
    products = products.filter(_stock_status_filter(stock_status))
    products = products.order_by("quantity", "name")
  else:
    products = products.order_by("name")
  if category:
    products = products.filter(category__name__icontains=category)

  total = products.count()
  rows = [_product_row(p) for p in products[:_limit(limit, 15)]]
  return {"total_matches": total, "showing": len(rows), "products": rows}


def get_product_details(business, product):
  p = _find_product(business, product)
  reorder = calculate_reorder(p, get_dispatch_stats(business))
  movements = StockMovement.objects.filter(business=business, product=p)[:10]
  return {
    **_product_row(p),
    "description": p.description,
    "lead_time_days": p.lead_time_days,
    "safety_stock": p.safety_stock,
    "reorder": {
      "method": reorder.method,
      "avg_daily_dispatch": reorder.avg_daily,
      "reorder_point": reorder.reorder_point,
      "suggested_quantity": reorder.suggested_quantity,
      "needs_reorder": reorder.needs_reorder,
    },
    "recent_movements": [
      {
        "date": m.created_at,
        "change": m.quantity_change,
        "balance_after": m.balance_after,
        "reason": m.get_reason_display(),
        "note": m.note,
      }
      for m in movements
    ],
  }


def get_stock_movements(business, product=None, reason=None, days=30, limit=20):
  since = timezone.now() - timedelta(days=_days(days))
  movements = (
    StockMovement.objects.filter(business=business, created_at__gte=since)
    .select_related("product")
  )
  if product:
    movements = movements.filter(product=_find_product(business, product))
  if reason:
    valid = {choice.value for choice in StockMovement.Reason}
    if reason not in valid:
      raise ToolError(f"reason must be one of: {', '.join(sorted(valid))}.")
    movements = movements.filter(reason=reason)

  totals = movements.aggregate(
    count=Count("id"),
    units_in=Coalesce(Sum("quantity_change", filter=Q(quantity_change__gt=0)), 0),
    units_out=Coalesce(Sum("quantity_change", filter=Q(quantity_change__lt=0)), 0),
  )
  rows = [
    {
      "date": m.created_at,
      "product": m.product.name,
      "sku": m.product.sku,
      "change": m.quantity_change,
      "balance_after": m.balance_after,
      "reason": m.get_reason_display(),
      "note": m.note,
    }
    for m in movements[:_limit(limit, 20)]
  ]
  return {"period_days": _days(days), **totals, "showing": len(rows), "movements": rows}


def get_dispatch_summary(business, days=30, outlet=None):
  since = timezone.localdate() - timedelta(days=_days(days))
  notes = DispatchNote.objects.filter(business=business, dispatch_date__gte=since)
  items = DispatchItem.objects.filter(
    dispatch_note__business=business, dispatch_note__dispatch_date__gte=since
  )
  if outlet:
    notes = notes.filter(outlet__name__icontains=outlet)
    items = items.filter(dispatch_note__outlet__name__icontains=outlet)

  top_products = (
    items.values("product__name", "product__sku")
    .annotate(units=Sum("quantity"))
    .order_by("-units")[:10]
  )
  by_outlet = (
    items.values("dispatch_note__outlet__name")
    .annotate(units=Sum("quantity"), dispatches=Count("dispatch_note", distinct=True))
    .order_by("-units")
  )
  return {
    "period_days": _days(days),
    "dispatch_notes": notes.count(),
    "total_units": items.aggregate(total=Coalesce(Sum("quantity"), 0))["total"],
    "top_products": [
      {"product": r["product__name"], "sku": r["product__sku"], "units": r["units"]}
      for r in top_products
    ],
    "by_outlet": [
      {"outlet": r["dispatch_note__outlet__name"], "units": r["units"], "dispatches": r["dispatches"]}
      for r in by_outlet
    ],
  }


def get_reorder_suggestions(business, include_closed=False, limit=20):
  suggestions = (
    ReorderSuggestion.objects.filter(business=business)
    .select_related("product", "rfq")
    .order_by("-created_at")
  )
  if not include_closed:
    suggestions = suggestions.filter(status__in=ReorderSuggestion.ACTIVE)
  rows = [
    {
      "product": s.product.name,
      "sku": s.product.sku,
      "status": s.get_status_display(),
      "current_quantity": s.product.quantity,
      "reorder_point": s.reorder_point,
      "suggested_quantity": s.suggested_quantity,
      "method": s.method,
      "rfq_number": _suggestion_rfq_number(s),
      "created_at": s.created_at,
    }
    for s in suggestions[:_limit(limit, 20)]
  ]
  return {"total": suggestions.count(), "showing": len(rows), "suggestions": rows}


def list_rfqs(business, status=None, limit=10):
  rfqs = RFQ.objects.filter(business=business)
  if _has_field(RFQ, "supply_category"):
    rfqs = rfqs.select_related("supply_category")
  rfqs = (
    rfqs.annotate(
      item_count=Count("items", distinct=True),
      suppliers_invited=Count("recipients", distinct=True),
      quotations_received=Count(
        "quotations",
        filter=~Q(quotations__status=Quotation.Status.WITHDRAWN),
        distinct=True,
      ),
    )
  )
  if status:
    valid = {choice.value for choice in RFQ.Status}
    if status not in valid:
      raise ToolError(f"status must be one of: {', '.join(sorted(valid))}.")
    rfqs = rfqs.filter(status=status)
  rows = [
    {
      "number": r.number,
      "status": r.get_status_display(),
      "supply_category": _rfq_category(r),
      "deadline": r.deadline,
      "items": r.item_count,
      "suppliers_invited": r.suppliers_invited,
      "quotations_received": r.quotations_received,
      "created_at": r.created_at,
    }
    for r in rfqs[:_limit(limit, 10)]
  ]
  return {"total": rfqs.count(), "showing": len(rows), "rfqs": rows}


def get_rfq_quotations(business, rfq_number):
  rfq = RFQ.objects.filter(business=business, number__iexact=(rfq_number or "").strip()).first()
  if rfq is None:
    raise ToolError(f"No RFQ found with number '{rfq_number}'. Use list_rfqs to see RFQ numbers.")
  quotations = (
    rfq.quotations.exclude(status=Quotation.Status.WITHDRAWN)
    .select_related("supplier_profile")
    .prefetch_related("items__rfq_item")
    .order_by("grand_total", "submitted_at")
  )
  return {
    "rfq_number": rfq.number,
    "rfq_status": rfq.get_status_display(),
    "deadline": rfq.deadline,
    "requested_items": [
      {"product": i.product_name, "sku": i.sku, "quantity": i.quantity} for i in rfq.items.all()
    ],
    "quotations": [
      {
        "supplier": q.supplier_profile.company_name,
        "status": q.get_status_display(),
        "subtotal": q.subtotal,
        "tax_total": q.tax_total,
        "grand_total": q.grand_total,
        "advance_amount": q.advance_amount,
        "delivery_date": q.delivery_date,
        "valid_until": q.valid_until,
        "items": [
          {
            "product": item.rfq_item.product_name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "gst_rate": item.gst_rate,
            "line_total": item.line_total,
          }
          for item in q.items.all()
        ],
      }
      for q in quotations
    ],
  }


def list_suppliers(business, query="", limit=15):
  suppliers = (
    Supplier.objects.filter(business=business, is_active=True)
    .select_related("linked_account")
    .prefetch_related("linked_account__categories")
  )
  if query:
    suppliers = suppliers.filter(
      Q(label__icontains=query)
      | Q(email__icontains=query)
      | Q(linked_account__company_name__icontains=query)
    )
  rows = []
  for s in suppliers[:_limit(limit, 15)]:
    profile = s.linked_account
    rows.append({
      "label": s.label,
      "email": s.email,
      "phone": s.phone,
      "company_name": profile.company_name if profile else None,
      "city": profile.city if profile else None,
      "verified": profile.is_verified if profile else False,
      "categories": [c.name for c in profile.categories.all()] if profile else [],
      "has_kosh_account": profile is not None,
    })
  return {"total": suppliers.count(), "showing": len(rows), "suppliers": rows}


def search_customers(business, query="", limit=15):
  customers = Customer.objects.filter(business=business, is_active=True)
  if query:
    customers = customers.filter(
      Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query)
    )
  rows = [
    {"name": c.name, "phone": c.phone, "email": c.email}
    for c in customers[:_limit(limit, 15)]
  ]
  return {"total": customers.count(), "showing": len(rows), "customers": rows}


def _related(obj, name):
  try:
    return getattr(obj, name)
  except ObjectDoesNotExist:
    return None


def _advance_state(po):
  if po.advance_amount <= 0:
    return "no advance needed"
  statuses = {p.status for p in po.payments.all() if p.kind == Payment.Kind.ADVANCE}
  if Payment.Status.PAID.value in statuses:
    return "advance paid"
  if Payment.Status.REFUNDED.value in statuses:
    return "advance refunded"
  if po.status == PurchaseOrder.Status.CANCELLED:
    return "advance not paid (order cancelled)"
  return "advance not paid yet"


NEXT_STEP = {
  PurchaseOrder.Status.AWAITING_ADVANCE.value: (
    "The owner must pay the advance before advance_due_by, otherwise Kosh cancels "
    "the order automatically."
  ),
  PurchaseOrder.Status.ISSUED.value: "Waiting for the supplier to dispatch the goods.",
  PurchaseOrder.Status.DISPATCHED.value: (
    "Goods are on the way. When they arrive, record a goods receipt for this order."
  ),
  PurchaseOrder.Status.CANCELLED.value: "Cancelled.",
}


def _invoice_next_step(invoice, po=None):
  po = po or invoice.purchase_order
  if po.status not in RECEIVED_STATUSES:
    return (
      "Goods not received yet. Record the goods receipt when the delivery arrives. "
      "The balance can only be paid after that, and it is reduced for any missing "
      "or rejected units."
    )
  if invoice.status == Invoice.Status.PAID:
    step = "Settled: nothing is left to pay on this invoice."
    if invoice.refund_due > 0:
      step += (
        " The advance was more than the accepted goods were worth, so the extra "
        "comes back to the owner (see refunds_to_owner)."
      )
    return step
  if invoice.balance_due > 0:
    return (
      "Goods received. The owner can now pay the balance online through Razorpay; "
      "Kosh then sends it to the supplier automatically."
    )
  return "Goods received; nothing is left to pay."


def _next_step(po, invoice=None):
  if po.status in RECEIVED_STATUSES:
    if invoice is None:
      return "Goods received."
    return _invoice_next_step(invoice, po)
  return NEXT_STEP.get(po.status, "")


def _payout_row(p):
  return {
    "purchase_order": p.purchase_order.number,
    "invoice": p.invoice.number,
    "supplier": p.supplier_profile.company_name,
    "kind": p.get_kind_display(),
    "status": p.get_status_display(),
    "gross_amount": p.gross_amount,
    "deducted_amount": p.deducted_amount,
    "amount": p.amount,
    "mode": p.mode or None,
    "utr": p.utr or None,
    "failure_reason": p.failure_reason or None,
    "sent_at": p.sent_at,
    "processed_at": p.processed_at,
  }


PAYOUT_MEANING = {
  Payout.Status.ON_HOLD.value: "Waiting for the supplier to add bank or UPI payout details.",
  Payout.Status.PENDING.value: "Queued to be sent.",
  Payout.Status.PROCESSING.value: "Sent to the bank, waiting for confirmation.",
  Payout.Status.PROCESSED.value: "Money reached the supplier.",
  Payout.Status.FAILED.value: (
    "Failed. The supplier must check and save their payout details again to retry."
  ),
}


def _payout_meaning(p):
  if p.status == Payout.Status.PROCESSED and p.amount <= 0:
    return "Nothing was sent: the whole amount went to repay an earlier overpayment."
  meaning = PAYOUT_MEANING.get(p.status, "")
  if p.deducted_amount > 0:
    meaning += " Part of it was held back to repay an earlier overpayment."
  return meaning


def _money_trail(invoice):
  payouts = invoice.payouts.select_related(
    "purchase_order", "invoice", "supplier_profile"
  ).order_by("created_at")
  return {
    "balance_payments": [
      {
        "status": p.get_status_display(),
        "amount": p.amount,
        "paid_at": p.paid_at,
        "failure_reason": p.failure_reason or None,
      }
      for p in invoice.payments.filter(kind=Payment.Kind.BALANCE).order_by("created_at")
    ],
    "supplier_payouts": [
      {**_payout_row(p), "meaning": _payout_meaning(p)} for p in payouts
    ],
    "refunds_to_owner": [
      {
        "amount": r.amount,
        "status": r.get_status_display(),
        "reason": (
          "Advance held by Kosh, refunded directly"
          if r.source == OwnerRefund.Source.HELD
          else "Recovered from the supplier's later payout"
        ),
        "failure_reason": r.failure_reason or None,
        "created_at": r.created_at,
      }
      for r in invoice.owner_refunds.order_by("created_at")
    ],
    "supplier_debts": [
      {
        "amount": d.amount,
        "recovered_amount": d.recovered_amount,
        "outstanding": d.outstanding,
        "status": d.get_status_display(),
        "meaning": (
          "The supplier received more advance than the accepted goods were worth; "
          "Kosh holds this back from their next payouts and refunds it to the owner."
        ),
      }
      for d in invoice.supplier_debts.order_by("created_at")
    ],
  }


def _order_queryset(business):
  return (
    PurchaseOrder.objects.filter(business=business)
    .select_related("supplier_profile", "rfq")
    .prefetch_related("payments")
  )


def _order_row(po):
  return {
    "number": po.number,
    "status": po.get_status_display(),
    "supplier": po.supplier_profile.company_name,
    "rfq_number": po.rfq.number,
    "delivery_date": po.delivery_date,
    "grand_total": po.grand_total,
    "advance_amount": po.advance_amount,
    "advance": _advance_state(po),
    "advance_due_by": (
      po.advance_due_by if po.status == PurchaseOrder.Status.AWAITING_ADVANCE else None
    ),
    "created_at": po.created_at,
  }


def list_purchase_orders(business, status=None, supplier=None, limit=10):
  orders = _order_queryset(business)
  if status:
    valid = {choice.value for choice in PurchaseOrder.Status}
    if status not in valid:
      raise ToolError(f"status must be one of: {', '.join(sorted(valid))}.")
    orders = orders.filter(status=status)
  if supplier:
    orders = orders.filter(supplier_profile__company_name__icontains=supplier)

  by_status = {
    row["status"]: row["count"]
    for row in PurchaseOrder.objects.filter(business=business)
    .values("status").annotate(count=Count("id"))
  }
  rows = [_order_row(po) for po in orders[:_limit(limit, 10)]]
  return {
    "total": orders.count(),
    "all_orders_by_status": by_status,
    "showing": len(rows),
    "orders": rows,
  }


def get_purchase_order(business, po_number):
  po = (
    _order_queryset(business)
    .prefetch_related("items")
    .filter(number__iexact=(po_number or "").strip())
    .first()
  )
  if po is None:
    raise ToolError(
      f"No purchase order found with number '{po_number}'. Use list_purchase_orders."
    )

  shipment = _related(po, "shipment")
  receipt = _related(po, "goods_receipt")
  invoice = _related(po, "invoice")
  shipped = {}
  if shipment:
    shipped = {i.purchase_order_item_id: i.quantity for i in shipment.items.all()}
  received = {}
  if receipt:
    received = {i.purchase_order_item_id: i for i in receipt.items.all()}

  items = []
  for item in po.items.all():
    got = received.get(item.id)
    items.append({
      "product": item.product_name,
      "sku": item.sku,
      "ordered": item.quantity,
      "shipped": shipped.get(item.id) if shipment else None,
      "received": got.received_quantity if got else None,
      "rejected": got.rejected_quantity if got else None,
      "unit_price": item.unit_price,
      "gst_rate": item.gst_rate,
      "line_total": item.line_total,
    })

  return {
    **_order_row(po),
    "next_step": _next_step(po, invoice),
    "items": items,
    "payments": [
      {
        "kind": p.get_kind_display(),
        "status": p.get_status_display(),
        "amount": p.amount,
        "paid_at": p.paid_at,
        "failure_reason": p.failure_reason,
      }
      for p in po.payments.all()
    ],
    "shipment": {
      "dispatched_at": shipment.dispatched_at,
      "expected_delivery_date": shipment.expected_delivery_date,
      "late_by_days": shipment.late_by_days,
      "tracking_note": shipment.tracking_note,
    } if shipment else None,
    "goods_receipt": {
      "number": receipt.number,
      "received_at": receipt.created_at,
      "issues": [
        {
          "product": d.receipt_item.purchase_order_item.product_name,
          "issue": d.get_kind_display(),
          "quantity": d.quantity,
        }
        for d in receipt.discrepancies.select_related("receipt_item__purchase_order_item")
      ],
    } if receipt else None,
    "invoice": {
      "number": invoice.number,
      "status": invoice.get_status_display(),
      "grand_total": invoice.grand_total,
      "advance_applied": invoice.advance_applied,
      "discrepancy_credit": invoice.discrepancy_credit,
      "balance_due": invoice.balance_due,
      "refund_due": invoice.refund_due,
    } if invoice else None,
    "supplier_payouts": [
      {**_payout_row(p), "meaning": _payout_meaning(p)}
      for p in po.payouts.select_related("purchase_order", "invoice", "supplier_profile")
      .order_by("created_at")
    ],
  }


INVOICE_STAGES = {
  "awaiting_goods_receipt": Q(
    status=Invoice.Status.UNPAID, purchase_order__status=PurchaseOrder.Status.DISPATCHED
  ),
  "ready_to_pay": Q(
    status=Invoice.Status.UNPAID,
    purchase_order__status__in=RECEIVED_STATUSES,
    balance_due__gt=0,
  ),
  "paid": Q(status=Invoice.Status.PAID),
}


def _invoice_stage(inv):
  if inv.status == Invoice.Status.PAID:
    return "paid"
  if inv.purchase_order.status in RECEIVED_STATUSES:
    return "ready_to_pay" if inv.balance_due > 0 else "settled"
  return "awaiting_goods_receipt"


def _invoice_queryset(business):
  return (
    Invoice.objects.filter(business=business)
    .select_related("supplier_profile", "purchase_order__goods_receipt")
    .order_by("-created_at")
  )


def _invoice_row(inv):
  receipt = _related(inv.purchase_order, "goods_receipt")
  return {
    "number": inv.number,
    "purchase_order": inv.purchase_order.number,
    "supplier": inv.supplier_profile.company_name,
    "status": inv.get_status_display(),
    "stage": _invoice_stage(inv),
    "issue_date": inv.issue_date,
    "goods_receipt": receipt.number if receipt else None,
    "grand_total": inv.grand_total,
    "advance_applied": inv.advance_applied,
    "discrepancy_credit": inv.discrepancy_credit,
    "balance_due": inv.balance_due,
    "refund_due": inv.refund_due,
  }


def list_invoices(business, status=None, stage=None, supplier=None, limit=10):
  invoices = _invoice_queryset(business)
  if status:
    valid = {choice.value for choice in Invoice.Status}
    if status not in valid:
      raise ToolError(f"status must be one of: {', '.join(sorted(valid))}.")
    invoices = invoices.filter(status=status)
  if stage:
    if stage not in INVOICE_STAGES:
      raise ToolError(f"stage must be one of: {', '.join(INVOICE_STAGES)}.")
    invoices = invoices.filter(INVOICE_STAGES[stage])
  if supplier:
    invoices = invoices.filter(supplier_profile__company_name__icontains=supplier)

  totals = invoices.aggregate(
    balance_due_total=_money_sum(F("balance_due")),
    refund_due_total=_money_sum(F("refund_due")),
  )
  ready = _invoice_queryset(business).filter(INVOICE_STAGES["ready_to_pay"])
  rows = [_invoice_row(inv) for inv in invoices[:_limit(limit, 10)]]
  return {
    "total": invoices.count(),
    **totals,
    "ready_to_pay_count": ready.count(),
    "ready_to_pay_total": ready.aggregate(total=_money_sum(F("balance_due")))["total"],
    "stage_meaning": {
      "awaiting_goods_receipt": "Supplier dispatched; goods receipt not recorded yet.",
      "ready_to_pay": "Goods received; the owner can pay the balance.",
      "paid": "Nothing left to pay.",
    },
    "note": "Invoice numbers restart for each supplier, so INV-0001 can exist for several suppliers.",
    "showing": len(rows),
    "invoices": rows,
  }


def _find_invoice(business, invoice_number, supplier=None):
  ref = (invoice_number or "").strip()
  if not ref:
    raise ToolError("Give an invoice number (e.g. INV-0001) or the purchase order number.")
  invoices = _invoice_queryset(business)
  if ref.upper().startswith("PO-"):
    matches = list(invoices.filter(purchase_order__number__iexact=ref)[:1])
    if not matches:
      raise ToolError(
        f"No invoice for purchase order '{ref}'. The supplier may not have dispatched it yet."
      )
    return matches[0]

  invoices = invoices.filter(number__iexact=ref)
  if supplier:
    invoices = invoices.filter(supplier_profile__company_name__icontains=supplier)
  matches = list(invoices[:6])
  if len(matches) == 1:
    return matches[0]
  if not matches:
    raise ToolError(f"No invoice found with number '{ref}'. Use list_invoices.")
  options = ", ".join(
    f"{m.number} from {m.supplier_profile.company_name} ({m.purchase_order.number})"
    for m in matches[:5]
  )
  raise ToolError(
    f"Several suppliers have an invoice numbered '{ref}': {options}. "
    "Ask which supplier, or use the purchase order number."
  )


def get_invoice(business, invoice_number, supplier=None):
  inv = _find_invoice(business, invoice_number, supplier)
  po = inv.purchase_order
  receipt = _related(po, "goods_receipt")
  return {
    **_invoice_row(inv),
    "purchase_order_status": po.get_status_display(),
    "subtotal": inv.subtotal,
    "tax_total": inv.tax_total,
    "advance_amount_on_order": po.advance_amount,
    "how_balance_is_worked_out": (
      "balance_due = grand_total - discrepancy_credit - advance_applied. "
      "discrepancy_credit is added at the goods receipt for units that were missing "
      "or rejected. refund_due is advance paid beyond what is payable."
    ),
    "next_step": _invoice_next_step(inv, po),
    "goods_receipt_date": receipt.created_at if receipt else None,
    "items": [
      {
        "product": i.product_name,
        "sku": i.sku,
        "quantity_invoiced": i.quantity,
        "unit_price": i.unit_price,
        "gst_rate": i.gst_rate,
        "line_total": i.line_total,
      }
      for i in inv.items.all()
    ],
    **_money_trail(inv),
  }


def _grn_queryset(business):
  return (
    GoodsReceipt.objects.filter(business=business)
    .select_related(
      "purchase_order__supplier_profile", "purchase_order__invoice", "received_by__profile"
    )
    .order_by("-created_at")
  )


def _user_name(user):
  if user is None:
    return None
  profile = getattr(user, "profile", None)
  return getattr(profile, "name", None) or user.get_full_name() or user.email


def list_goods_receipts(business, days=None, supplier=None, with_issues_only=False, limit=10):
  receipts = _grn_queryset(business)
  period = None
  if days:
    period = _days(days)
    receipts = receipts.filter(created_at__gte=timezone.now() - timedelta(days=period))
  if supplier:
    receipts = receipts.filter(
      purchase_order__supplier_profile__company_name__icontains=supplier
    )
  if with_issues_only:
    receipts = receipts.filter(discrepancies__isnull=False).distinct()
  receipts = receipts.prefetch_related("items", "discrepancies")

  awaiting = PurchaseOrder.objects.filter(
    business=business, status=PurchaseOrder.Status.DISPATCHED
  ).select_related("supplier_profile", "shipment")

  rows = []
  for grn in receipts[:_limit(limit, 10)]:
    po = grn.purchase_order
    invoice = _related(po, "invoice")
    items = list(grn.items.all())
    received = sum(i.received_quantity for i in items)
    rejected = sum(i.rejected_quantity for i in items)
    rows.append({
      "number": grn.number,
      "purchase_order": po.number,
      "supplier": po.supplier_profile.company_name,
      "received_at": grn.created_at,
      "received_by": _user_name(grn.received_by),
      "units_received": received,
      "units_rejected": rejected,
      "units_accepted_into_stock": received - rejected,
      "issues": len(grn.discrepancies.all()),
      "credit_total": sum((i.credit_amount for i in items), Decimal("0")),
      "invoice_number": invoice.number if invoice else None,
      "invoice_status": invoice.get_status_display() if invoice else None,
    })
  return {
    "period_days": period,
    "total": receipts.count(),
    "showing": len(rows),
    "goods_receipts": rows,
    "dispatched_orders_waiting_for_goods_receipt": [
      {
        "purchase_order": po.number,
        "supplier": po.supplier_profile.company_name,
        "expected_delivery_date": (
          po.shipment.expected_delivery_date if _related(po, "shipment") else None
        ),
      }
      for po in awaiting[:10]
    ],
  }


def get_goods_receipt(business, grn_number):
  ref = (grn_number or "").strip()
  if not ref:
    raise ToolError("Give a goods receipt number (e.g. GRN-0001) or the purchase order number.")
  receipts = _grn_queryset(business)
  if ref.upper().startswith("PO-"):
    grn = receipts.filter(purchase_order__number__iexact=ref).first()
    if grn is None:
      raise ToolError(f"No goods receipt has been recorded for '{ref}' yet.")
  else:
    grn = receipts.filter(number__iexact=ref).first()
    if grn is None:
      raise ToolError(f"No goods receipt found with number '{ref}'. Use list_goods_receipts.")

  po = grn.purchase_order
  invoice = _related(po, "invoice")
  items = grn.items.select_related("purchase_order_item").prefetch_related("discrepancies")
  return {
    "number": grn.number,
    "purchase_order": po.number,
    "purchase_order_status": po.get_status_display(),
    "supplier": po.supplier_profile.company_name,
    "received_at": grn.created_at,
    "received_by": _user_name(grn.received_by),
    "notes": grn.notes or None,
    "items": [
      {
        "product": i.purchase_order_item.product_name,
        "sku": i.purchase_order_item.sku,
        "ordered": i.ordered_quantity,
        "dispatched": i.dispatched_quantity,
        "received": i.received_quantity,
        "rejected": i.rejected_quantity,
        "accepted_into_stock": i.accepted_quantity,
        "credit_amount": i.credit_amount,
        "note": i.note or None,
        "issues": [
          {"issue": d.get_kind_display(), "quantity": d.quantity}
          for d in i.discrepancies.all()
        ],
      }
      for i in items
    ],
    "stock_note": "Only accepted units (received minus rejected) were added to stock.",
    "invoice": {
      "number": invoice.number,
      "status": invoice.get_status_display(),
      "grand_total": invoice.grand_total,
      "discrepancy_credit": invoice.discrepancy_credit,
      "advance_applied": invoice.advance_applied,
      "balance_due": invoice.balance_due,
      "refund_due": invoice.refund_due,
      "next_step": _invoice_next_step(invoice, po),
    } if invoice else None,
  }


def list_supplier_payouts(business, status=None, supplier=None, limit=15):
  payouts = (
    Payout.objects.filter(purchase_order__business=business)
    .select_related("purchase_order", "invoice", "supplier_profile")
    .order_by("-created_at")
  )
  if status:
    valid = {choice.value for choice in Payout.Status}
    if status not in valid:
      raise ToolError(f"status must be one of: {', '.join(sorted(valid))}.")
    payouts = payouts.filter(status=status)
  if supplier:
    payouts = payouts.filter(supplier_profile__company_name__icontains=supplier)

  by_status = {
    row["status"]: {"count": row["count"], "amount": row["amount"]}
    for row in payouts.order_by().values("status").annotate(
      count=Count("id"), amount=_money_sum(F("amount"))
    )
  }
  debts = SupplierDebt.objects.filter(
    purchase_order__business=business, status=SupplierDebt.Status.OPEN
  ).select_related("supplier_profile", "purchase_order")
  refunds = OwnerRefund.objects.filter(
    invoice__business=business
  ).select_related("invoice").order_by("-created_at")
  if supplier:
    debts = debts.filter(supplier_profile__company_name__icontains=supplier)
    refunds = refunds.filter(invoice__supplier_profile__company_name__icontains=supplier)

  rows = [
    {**_payout_row(p), "meaning": _payout_meaning(p)}
    for p in payouts[:_limit(limit, 15)]
  ]
  return {
    "how_it_works": (
      "Kosh pays suppliers automatically through RazorpayX: the advance when the "
      "supplier dispatches, the balance after the owner pays it. deducted_amount was "
      "held back to recover an earlier overpayment; amount is what was actually sent."
    ),
    "total": payouts.count(),
    "by_status": by_status,
    "showing": len(rows),
    "payouts": rows,
    "open_supplier_debts": [
      {
        "supplier": d.supplier_profile.company_name,
        "purchase_order": d.purchase_order.number,
        "amount": d.amount,
        "recovered_amount": d.recovered_amount,
        "outstanding": d.outstanding,
      }
      for d in debts[:10]
    ],
    "refunds_to_owner": [
      {
        "invoice": r.invoice.number,
        "amount": r.amount,
        "status": r.get_status_display(),
        "reason": (
          "Advance held by Kosh, refunded directly"
          if r.source == OwnerRefund.Source.HELD
          else "Recovered from the supplier's later payout"
        ),
        "created_at": r.created_at,
      }
      for r in refunds[:10]
    ],
  }


def get_receiving_issues(business, days=30, supplier=None, limit=15):
  days = _days(days)
  since = timezone.now() - timedelta(days=days)
  receipts = GoodsReceipt.objects.filter(business=business, created_at__gte=since)
  issues = GoodsReceiptDiscrepancy.objects.filter(
    goods_receipt__business=business, goods_receipt__created_at__gte=since
  )
  if supplier:
    supplier_filter = {
      "purchase_order__supplier_profile__company_name__icontains": supplier
    }
    receipts = receipts.filter(**supplier_filter)
    issues = issues.filter(**{f"goods_receipt__{k}": v for k, v in supplier_filter.items()})

  kinds = dict(GoodsReceiptDiscrepancy.Kind.choices)
  by_supplier = {}
  for row in (
    issues.values("goods_receipt__purchase_order__supplier_profile__company_name", "kind")
    .annotate(units=Sum("quantity"))
  ):
    name = row["goods_receipt__purchase_order__supplier_profile__company_name"]
    by_supplier.setdefault(name, {})[kinds[row["kind"]]] = row["units"]

  recent = issues.select_related(
    "goods_receipt__purchase_order__supplier_profile",
    "receipt_item__purchase_order_item",
  ).order_by("-goods_receipt__created_at")[:_limit(limit, 15)]
  return {
    "period_days": days,
    "goods_receipts": receipts.count(),
    "receipts_with_issues": receipts.filter(discrepancies__isnull=False).distinct().count(),
    "credit_total": receipts.aggregate(
      total=_money_sum(F("items__credit_amount"))
    )["total"],
    "issue_units_by_supplier": by_supplier,
    "recent_issues": [
      {
        "date": d.goods_receipt.created_at,
        "goods_receipt": d.goods_receipt.number,
        "purchase_order": d.goods_receipt.purchase_order.number,
        "supplier": d.goods_receipt.purchase_order.supplier_profile.company_name,
        "product": d.receipt_item.purchase_order_item.product_name,
        "issue": d.get_kind_display(),
        "quantity": d.quantity,
      }
      for d in recent
    ],
  }


def _activity_counts(queryset, user_field, user_ids, since):
  rows = (
    queryset.filter(**{f"{user_field}__in": user_ids, "created_at__gte": since})
    .values(user_field).annotate(count=Count("pk"))
  )
  return {row[user_field]: row["count"] for row in rows}


def list_employees(business, days=30):
  days = _days(days)
  since = timezone.now() - timedelta(days=days)
  employees = list(
    Employee.objects.filter(business=business)
    .select_related("user__profile")
    .order_by("created_at")
  )
  user_ids = [e.user_id for e in employees]
  stock = _activity_counts(
    StockMovement.objects.filter(business=business), "created_by", user_ids, since
  )
  dispatches = _activity_counts(
    DispatchNote.objects.filter(business=business), "created_by", user_ids, since
  )
  receipts = _activity_counts(
    GoodsReceipt.objects.filter(business=business), "received_by", user_ids, since
  )

  rows = []
  for e in employees:
    profile = getattr(e.user, "profile", None)
    rows.append({
      "name": getattr(profile, "name", None) or e.user.get_full_name() or None,
      "email": e.user.email,
      "phone": e.phone,
      "active": e.is_active,
      "joined_on": e.created_at,
      "activity_last_period": {
        "stock_changes": stock.get(e.user_id, 0),
        "dispatch_notes": dispatches.get(e.user_id, 0),
        "goods_receipts": receipts.get(e.user_id, 0),
      },
    })

  invites = EmployeeInvite.objects.filter(
    business=business, status="pending", created_at__gte=invite_cutoff()
  ).order_by("-created_at")
  return {
    "period_days": days,
    "employee_count": len(rows),
    "employees": rows,
    "pending_invites": [
      {"email": i.email, "phone": i.phone, "sent_on": i.created_at} for i in invites
    ],
    "note": "Removed employees are deleted, so they are not listed. Invites expire after 14 days.",
  }


TOOL_FUNCTIONS = {
  "get_app_help": get_app_help,
  "get_business_insights": get_business_insights,
  "get_inventory_overview": get_inventory_overview,
  "search_products": search_products,
  "get_product_details": get_product_details,
  "get_stock_movements": get_stock_movements,
  "get_dispatch_summary": get_dispatch_summary,
  "get_reorder_suggestions": get_reorder_suggestions,
  "list_rfqs": list_rfqs,
  "get_rfq_quotations": get_rfq_quotations,
  "list_suppliers": list_suppliers,
  "search_customers": search_customers,
  "list_purchase_orders": list_purchase_orders,
  "get_purchase_order": get_purchase_order,
  "list_invoices": list_invoices,
  "get_invoice": get_invoice,
  "list_goods_receipts": list_goods_receipts,
  "get_goods_receipt": get_goods_receipt,
  "list_supplier_payouts": list_supplier_payouts,
  "get_receiving_issues": get_receiving_issues,
  "list_employees": list_employees,
}

_LIMIT = {"type": "INTEGER", "description": f"Max rows to return (1-{MAX_LIMIT})."}
_DAYS = {"type": "INTEGER", "description": "How many days back to look. Default 30."}

TOOL_DECLARATIONS = [
  {
    "name": "get_app_help",
    "description": (
      "The official guide to how Kosh works: roles and what each role (owner, employee, "
      "supplier) can and cannot do, available features, features that do NOT exist, and "
      "screen names. Call this for ANY question about how Kosh works, permissions, who can "
      "see or do something, or where to find something in the app."
    ),
  },
  {
    "name": "get_business_insights",
    "description": (
      "One-call business health check: inventory overview, products needing restock, "
      "top dispatched products, dispatch per outlet, slow-moving stock, damaged units, "
      "and procurement status (open RFQs, RFQs with no quotes, reorder alerts). Use this "
      "for broad questions like 'give me insights' or 'how is my business doing'."
    ),
    "parameters": {"type": "OBJECT", "properties": {"days": _DAYS}},
  },
  {
    "name": "get_inventory_overview",
    "description": (
      "Headline numbers for the business's warehouse: product count, total units, "
      "out-of-stock and low-stock counts, stock value at cost and selling price, "
      "open reorder alerts."
    ),
  },
  {
    "name": "search_products",
    "description": (
      "Find products by name/SKU and/or stock status. Use stock_status='low_stock' or "
      "'out_of_stock' to list items that need restocking."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "query": {"type": "STRING", "description": "Part of a product name or SKU."},
        "stock_status": {
          "type": "STRING",
          "enum": ["in_stock", "low_stock", "out_of_stock"],
        },
        "category": {"type": "STRING", "description": "Category name (partial match)."},
        "include_inactive": {"type": "BOOLEAN"},
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "get_product_details",
    "description": (
      "Full details for ONE product: stock, prices, reorder point and suggested reorder "
      "quantity, and its last 10 stock movements."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {"product": {"type": "STRING", "description": "Product SKU or name."}},
      "required": ["product"],
    },
  },
  {
    "name": "get_stock_movements",
    "description": (
      "Stock ledger entries (stock in/out) over a period, optionally for one product or "
      "one reason. Returns totals in/out plus the latest entries."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "product": {"type": "STRING", "description": "Product SKU or name."},
        "reason": {
          "type": "STRING",
          "enum": ["opening_balance", "grn_received", "dispatch", "damaged", "adjustment"],
        },
        "days": _DAYS,
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "get_dispatch_summary",
    "description": (
      "Dispatches to outlets over a period: number of dispatch notes, total units, "
      "top dispatched products and a per-outlet breakdown."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "days": _DAYS,
        "outlet": {"type": "STRING", "description": "Outlet name (partial match)."},
      },
    },
  },
  {
    "name": "get_reorder_suggestions",
    "description": "Reorder alerts Kosh has raised for products running low, with suggested quantities.",
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "include_closed": {"type": "BOOLEAN", "description": "Also include closed alerts."},
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "list_rfqs",
    "description": "Requests for quotation (RFQs) sent to suppliers, with invite and quotation counts.",
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "status": {"type": "STRING", "enum": ["open", "closed", "awarded", "cancelled"]},
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "get_rfq_quotations",
    "description": (
      "All supplier quotations for one RFQ, cheapest first, with totals, advance amount, "
      "delivery date and per-item prices. Use this to compare suppliers."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {"rfq_number": {"type": "STRING", "description": "e.g. RFQ-0003"}},
      "required": ["rfq_number"],
    },
  },
  {
    "name": "list_suppliers",
    "description": "The business's suppliers with contact details, city, categories and verification.",
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "query": {"type": "STRING", "description": "Name, label or email (partial match)."},
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "search_customers",
    "description": "Look up the business's customers by name, phone or email.",
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "query": {"type": "STRING"},
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "list_purchase_orders",
    "description": (
      "Purchase orders (PO-0001, ...) with supplier, status, delivery date and advance "
      "payment state, plus a count of all orders by status. Use for 'which orders are "
      "waiting for the advance / not dispatched / on the way'."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "status": {
          "type": "STRING",
          "enum": [
            "awaiting_advance", "issued", "dispatched",
            "partially_received", "received", "cancelled",
          ],
        },
        "supplier": {"type": "STRING", "description": "Supplier company name (partial match)."},
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "get_purchase_order",
    "description": (
      "Everything about ONE purchase order: items (ordered, shipped, received, rejected), "
      "advance payments, shipment and expected delivery, goods receipt issues, invoice, "
      "and the next step."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {"po_number": {"type": "STRING", "description": "e.g. PO-0003"}},
      "required": ["po_number"],
    },
  },
  {
    "name": "list_invoices",
    "description": (
      "Supplier invoices (created automatically when a supplier dispatches) with stage, "
      "goods receipt number, balance due, advance applied, discrepancy credit and refund "
      "due, plus totals and how much is ready to pay now. Use for 'how much do I owe "
      "suppliers', 'which invoices can I pay', 'which invoices are waiting for delivery'."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "status": {"type": "STRING", "enum": ["unpaid", "paid"]},
        "stage": {
          "type": "STRING",
          "enum": ["awaiting_goods_receipt", "ready_to_pay", "paid"],
          "description": (
            "awaiting_goods_receipt = dispatched but not received yet; "
            "ready_to_pay = received, balance can be paid now."
          ),
        },
        "supplier": {"type": "STRING", "description": "Supplier company name (partial match)."},
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "get_invoice",
    "description": (
      "Everything about ONE supplier invoice: items, totals, how the balance was worked "
      "out, the next step, balance payments, payouts sent to the supplier, refunds to the "
      "owner and any amount the supplier owes back. Invoice numbers restart per supplier, "
      "so pass supplier when known, or pass the PO number (e.g. PO-0003) instead."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "invoice_number": {
          "type": "STRING", "description": "e.g. INV-0002, or the order number PO-0003.",
        },
        "supplier": {"type": "STRING", "description": "Supplier company name (partial match)."},
      },
      "required": ["invoice_number"],
    },
  },
  {
    "name": "list_goods_receipts",
    "description": (
      "Goods receipts (GRN-0001, ...) recorded when deliveries arrived: order, supplier, "
      "who received it, units received / rejected / accepted into stock, issue count and "
      "the invoice. Also lists dispatched orders still waiting for a goods receipt."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "days": {
          "type": "INTEGER",
          "description": "Only receipts from the last N days. Leave out for all receipts.",
        },
        "supplier": {"type": "STRING", "description": "Supplier company name (partial match)."},
        "with_issues_only": {
          "type": "BOOLEAN", "description": "Only receipts with missing, rejected or extra units.",
        },
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "get_goods_receipt",
    "description": (
      "Everything about ONE goods receipt: per item ordered, dispatched, received, "
      "rejected, accepted into stock, issues and notes, plus its effect on the invoice."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "grn_number": {
          "type": "STRING", "description": "e.g. GRN-0004, or the order number PO-0003.",
        },
      },
      "required": ["grn_number"],
    },
  },
  {
    "name": "list_supplier_payouts",
    "description": (
      "Money Kosh has sent (or is sending) to suppliers through RazorpayX: advance and "
      "balance payouts with status (on hold, pending, processing, processed, failed), "
      "bank reference (UTR), amounts held back; open amounts suppliers owe back; refunds "
      "to the owner. Use for 'did the supplier get paid', 'why is a payout stuck'."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "status": {
          "type": "STRING",
          "enum": ["on_hold", "pending", "processing", "processed", "failed"],
        },
        "supplier": {"type": "STRING", "description": "Supplier company name (partial match)."},
        "limit": _LIMIT,
      },
    },
  },
  {
    "name": "list_employees",
    "description": (
      "The business's employees (name, email, phone, active, joined date) with how many "
      "stock changes, dispatch notes and goods receipts each recorded in the period, plus "
      "pending employee invites."
    ),
    "parameters": {"type": "OBJECT", "properties": {"days": _DAYS}},
  },
  {
    "name": "get_receiving_issues",
    "description": (
      "Problems found when goods were received: short shipped, short received, rejected or "
      "damaged, excess. Totals per supplier and the latest issues."
    ),
    "parameters": {
      "type": "OBJECT",
      "properties": {
        "days": _DAYS,
        "supplier": {"type": "STRING", "description": "Supplier company name (partial match)."},
        "limit": _LIMIT,
      },
    },
  },
]



OWNER_ONLY_TOOLS = {
  "get_rfq_quotations", "list_invoices", "get_invoice", "list_supplier_payouts",
  "list_employees",
}

PRICE_FIELDS = {
  "price", "cost_price", "unit_price", "gst_rate",
  "subtotal", "tax_total", "grand_total", "advance_amount", "line_total",
  "line_subtotal", "line_tax", "amount", "balance_amount",
  "advance_applied", "discrepancy_credit", "balance_due", "refund_due",
  "credit_amount", "credit_total", "unpaid_invoice_balance",
  "balance_due_total", "refund_due_total",
  "stock_value_at_selling_price", "stock_value_at_cost", "products_without_cost_price",
  "gross_amount", "deducted_amount", "recovered_amount", "outstanding",
  "advance_amount_on_order", "ready_to_pay_total", "balance_ready_to_pay",
  "supplier_payments", "supplier_payouts", "balance_payments", "refunds_to_owner",
  "supplier_debts", "open_supplier_debts", "invoice", "invoice_status",
}


def declarations_for(is_owner):
  if is_owner:
    return TOOL_DECLARATIONS
  return [d for d in TOOL_DECLARATIONS if d["name"] not in OWNER_ONLY_TOOLS]


def redact_prices(data):
  if isinstance(data, dict):
    return {k: redact_prices(v) for k, v in data.items() if k not in PRICE_FIELDS}
  if isinstance(data, list):
    return [redact_prices(item) for item in data]
  return data


def execute_tool(name, args, business, is_owner=True):
  func = TOOL_FUNCTIONS.get(name)
  if func is None:
    return {"error": f"Unknown tool '{name}'."}
  if not is_owner and name in OWNER_ONLY_TOOLS:
    return {"error": "Only the business owner can see this information."}
  args = dict(args or {})
  try:
    inspect.signature(func).bind(business, **args)
  except TypeError:
    return {"error": f"Invalid arguments for '{name}': {sorted(args)}."}
  try:
    result = func(business, **args)
  except ToolError as exc:
    return {"error": str(exc)}
  result = to_json_safe(result)
  return result if is_owner else redact_prices(result)