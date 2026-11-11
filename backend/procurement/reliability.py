from collections import defaultdict
from django.utils import timezone
from .models import GoodsReceiptItem, PurchaseOrder

WEIGHTS={"on_time": 0.40, "fill": 0.35, "clean": 0.25}

PRIOR=0.5
PRIOR_ORDERS=3

def _late_days(promised, expected, dispatched_at):
    if expected is None or dispatched_at is None:
        return 0
    arrives=max(expected, timezone.localtime(dispatched_at).date())
    return max((arrives-promised).days, 0)

def score_from_counts(orders, late_orders, ordered_units, accepted_units, clean_orders):
    on_time=1-late_orders/orders
    fill=accepted_units/ordered_units if ordered_units else 1.0
    clean=clean_orders/orders
    raw=(
        WEIGHTS["on_time"]*on_time
        +WEIGHTS["fill"]*fill
        +WEIGHTS["clean"]*clean
    )
    score=(orders*raw+PRIOR_ORDERS*PRIOR)/(orders+PRIOR_ORDERS)
    return {
        "score": score,
        "orders": orders,
        "on_time_rate": on_time,
        "fill_rate": fill,
        "clean_rate": clean,
    }

def reliability_stats(supplier_ids):
    ids=list(set(supplier_ids))
    if not ids:
        return {}
    
    orders=PurchaseOrder.objects.filter(
        supplier_profile_id__in=ids,
        goods_receipt__isnull=False
    ).values_list(
        "id", "supplier_profile_id", "delivery_date", 
        "shipment__expected_delivery_date", "shipment__dispatched_at",
    )

    lines = GoodsReceiptItem.objects.filter(
    goods_receipt__purchase_order__supplier_profile_id__in=ids
    ).values_list(
        "goods_receipt__purchase_order_id",
        "ordered_quantity", "dispatched_quantity",
        "received_quantity", "rejected_quantity",
    )

    per_order = defaultdict(lambda: {"ordered": 0, "accepted": 0, "clean": True})
    for order_id, ordered, dispatched, received, rejected in lines:
        row = per_order[order_id]
        row["ordered"] += ordered
        row["accepted"] += min(received - rejected, ordered)
        if dispatched < ordered or received < dispatched or rejected > 0:
            row["clean"] = False

    totals = defaultdict(
        lambda: {"orders": 0, "late": 0, "ordered": 0, "accepted": 0, "clean": 0}
    )
    for order_id, supplier_id, promised, expected, dispatched_at in orders:
        total = totals[supplier_id]
        row = per_order[order_id]
        total["orders"] += 1
        if _late_days(promised, expected, dispatched_at) > 0:
            total["late"] += 1
        total["ordered"] += row["ordered"]
        total["accepted"] += row["accepted"]
        if row["clean"]:
            total["clean"] += 1

    return {
        supplier_id: score_from_counts(
        t["orders"], t["late"], t["ordered"], t["accepted"], t["clean"]
        )
        for supplier_id, t in totals.items()
    }

def reliability_summary(stats):
  if stats is None:
    return None
  return {
    "score": round(stats["score"] * 100, 1),
    "orders": stats["orders"],
    "on_time_rate": round(stats["on_time_rate"] * 100, 1),
    "fill_rate": round(stats["fill_rate"] * 100, 1),
    "clean_rate": round(stats["clean_rate"] * 100, 1),
  }

