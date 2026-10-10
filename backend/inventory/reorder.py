import math
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Min, Q, Sum
from django.utils import timezone

from .models import StockMovement

WINDOW_DAYS = 30
MIN_HISTORY_DAYS = 14
MIN_DISPATCHES = 3
COVER_DAYS = 30


@dataclass
class ReorderResult:
  product_id: object
  method: str
  avg_daily: float
  reorder_point: int
  suggested_quantity: int
  needs_reorder: bool


def get_dispatch_stats(business, now=None):
  """One query for ALL products of a business: {product_id: row}."""
  now = now or timezone.now()
  since = now - timedelta(days=WINDOW_DAYS)
  rows = (
    StockMovement.objects.filter(
      business=business, reason=StockMovement.Reason.DISPATCH
    )
    .values("product_id")
    .annotate(
      first=Min("created_at"),
      total=Sum("quantity_change", filter=Q(created_at__gte=since)),
      count=Count("id", filter=Q(created_at__gte=since)),
    )
  )
  return {row["product_id"]: row for row in rows}


def calculate_reorder(product, stats, now=None):
  now = now or timezone.now()
  row = stats.get(product.id)

  method = "manual"
  avg_daily = 0.0
  if row and row["total"] and row["count"] >= MIN_DISPATCHES:
    history_days = min(WINDOW_DAYS, (now - row["first"]).days)
    if history_days >= MIN_HISTORY_DAYS:
      method = "formula"
      avg_daily = abs(row["total"]) / history_days  # dispatches are negative

  if method == "formula":
    reorder_point = math.ceil(avg_daily * product.lead_time_days) + product.safety_stock
    target = avg_daily * (product.lead_time_days + COVER_DAYS) + product.safety_stock
    suggested = math.ceil(target - product.quantity)
  else:
    reorder_point = product.low_stock_threshold
    suggested = product.reorder_quantity or (2 * product.low_stock_threshold - product.quantity)

  suggested = max(suggested, 0)
  return ReorderResult(
    product_id=product.id,
    method=method,
    avg_daily=round(avg_daily, 2),
    reorder_point=reorder_point,
    suggested_quantity=suggested,
    needs_reorder=product.quantity <= reorder_point and suggested > 0,
  )
