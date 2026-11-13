from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .models import PurchaseOrder, PurchaseOrderItem

HISTORY_DAYS = 365
RECENT_DAYS = 90
SAME_BAND = Decimal("1.0")
CENT = Decimal("0.01")
TENTH = Decimal("0.1")


def _money(value):
  return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def price_history(business, product_ids, exclude_rfq_id=None):
  
  now = timezone.now()
  rows = PurchaseOrderItem.objects.filter(
    purchase_order__business=business,
    purchase_order__status__in=PurchaseOrder.SUPPLIER_VISIBLE,
    purchase_order__created_at__gte=now - timedelta(days=HISTORY_DAYS),
    product_id__in=list(product_ids),
  )
  if exclude_rfq_id is not None:
    rows = rows.exclude(purchase_order__rfq_id=exclude_rfq_id)
  rows = rows.order_by("-purchase_order__created_at").values_list(
    "product_id", "unit_price", "purchase_order__created_at"
  )

  recent_cutoff = now - timedelta(days=RECENT_DAYS)
  seen = {}
  for product_id, unit_price, created_at in rows:
    entry = seen.setdefault(product_id, {"last_price": unit_price, "recent": []})
    if created_at >= recent_cutoff:
      entry["recent"].append(unit_price)

  history = {}
  for product_id, entry in seen.items():
    recent = entry["recent"]
    history[product_id] = {
      "last_price": entry["last_price"],
      "recent_count": len(recent),
      "recent_low": min(recent) if recent else None,
      "recent_avg": sum(recent) / len(recent) if recent else None,
    }
  return history


def compare_price(unit_price, history):
  if not history or history["last_price"] <= 0:
    return None
  last = history["last_price"]
  pct = ((unit_price - last) / last * 100).quantize(TENTH, rounding=ROUND_HALF_UP)
  low = history["recent_low"]
  avg = history["recent_avg"]

  if history["recent_count"] >= 2 and unit_price <= low:
    tag, label = "lowest_90d", "Lowest price in 90 days"
  elif abs(pct) < SAME_BAND:
    tag, label = "same_as_last", "Same as your last purchase"
  elif pct > 0:
    tag, label = "above_last", f"{float(abs(pct)):g}% above your last purchase"
  else:
    tag, label = "below_last", f"{float(abs(pct)):g}% below your last purchase"

  return {
    "tag": tag,
    "label": label,
    "last_price": _money(last),
    "vs_last_pct": float(pct),
    "avg_90d": _money(avg) if avg is not None else None,
    "low_90d": _money(low) if low is not None else None,
    "purchases_90d": history["recent_count"],
  }
