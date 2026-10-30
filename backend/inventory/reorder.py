import math
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Min, Q, Sum
from django.utils import timezone

from .models import StockMovement

from statistics import NormalDist
from django.db.models.functions import TruncDate

SERVICE_LEVEL=0.95
Z=NormalDist().inv_cdf(SERVICE_LEVEL)
PROCESS_DAYS=4

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
  std_daily: float=0.0


def get_dispatch_stats(business, now=None):

  now = now or timezone.now()
  since = now - timedelta(days=WINDOW_DAYS)
  base = StockMovement.objects.filter(
    business=business, reason=StockMovement.Reason.DISPATCH
  )
  rows = {
    row["product_id"]: row
    for row in base.values("product_id").annotate(
      first=Min("created_at"),
      total=Sum("quantity_change", filter=Q(created_at__gte=since)),
      count=Count("id", filter=Q(created_at__gte=since)),
    )
  }
  daily = (
    base.filter(created_at__gte=since)
    .annotate(day=TruncDate("created_at"))
    .values("product_id", "day")
    .annotate(qty=Sum("quantity_change"))
  )
  for item in daily:
    row = rows.get(item["product_id"])
    if row is not None:
      row.setdefault("daily", []).append(abs(item["qty"]))
  return rows

def calculate_reorder(product, stats, now=None):
  now = now or timezone.now()
  row = stats.get(product.id)

  method = "manual"
  avg_daily = 0.0
  std_daily = 0.0
  if row and row["total"] and row["count"] >= MIN_DISPATCHES:
    history_days = min(WINDOW_DAYS, (now - row["first"]).days)
    if history_days >= MIN_HISTORY_DAYS:
      method = "formula"
      avg_daily = abs(row["total"]) / history_days
      sum_sq = sum(q * q for q in row.get("daily", []))
      variance = (sum_sq - history_days * avg_daily ** 2) / (history_days - 1)
      std_daily = math.sqrt(max(variance, 0.0))

  if method == "formula":
    lead_days = product.lead_time_days + PROCESS_DAYS
    safety = max(product.safety_stock, math.ceil(Z * std_daily * math.sqrt(lead_days)))
    reorder_point = math.ceil(avg_daily * lead_days) + safety
    target = avg_daily * (lead_days + COVER_DAYS) + safety
    suggested = math.ceil(target - product.quantity)
    if suggested > 0 and product.reorder_quantity:
      suggested = max(suggested, product.reorder_quantity)
  else:
    reorder_point = product.low_stock_threshold
    deficit = 2 * product.low_stock_threshold - product.quantity
    suggested = max(product.reorder_quantity or 0, deficit, 1)

  suggested = max(suggested, 0)
  return ReorderResult(
    product_id=product.id,
    method=method,
    avg_daily=round(avg_daily, 2),
    reorder_point=reorder_point,
    suggested_quantity=suggested,
    needs_reorder=product.quantity <= reorder_point and suggested > 0,
    std_daily=round(std_daily, 2),
  )
