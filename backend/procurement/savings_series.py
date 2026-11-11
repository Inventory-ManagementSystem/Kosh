from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .savings_services import ZERO, _money, savings_summary

GROUPS = ("day", "week", "month")


def default_group(days):
  if days <= 31:
    return "day"
  if days <= 120:
    return "week"
  return "month"


def _bucket_start(day, group_by):
  if group_by == "week":
    return day - timedelta(days=day.weekday())  # weeks start on Monday
  if group_by == "month":
    return day.replace(day=1)
  return day


def _next_bucket(start, group_by):
  if group_by == "week":
    return start + timedelta(days=7)
  if group_by == "month":
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
  return start + timedelta(days=1)


def savings_series(business, days, group_by=None):
  group_by = group_by or default_group(days)
  if group_by not in GROUPS:
    raise ValueError(f"group_by must be one of {GROUPS}.")

  summary = savings_summary(business, days)

  first = _bucket_start(
    timezone.localdate(timezone.now() - timedelta(days=days)), group_by
  )
  last = _bucket_start(timezone.localdate(), group_by)
  buckets = {}
  start = first
  while start <= last:
    buckets[start] = {"savings": ZERO, "orders": 0}
    start = _next_bucket(start, group_by)

  for order in summary["orders"]:
    day = timezone.localtime(order["ordered_at"]).date()
    key = max(_bucket_start(day, group_by), first)
    buckets[key]["savings"] += Decimal(order["savings"])
    buckets[key]["orders"] += 1

  running = ZERO
  points = []
  for start, bucket in buckets.items():
    running += bucket["savings"]
    points.append({
      "period_start": start.isoformat(),
      "savings": str(_money(bucket["savings"])),
      "cumulative": str(_money(running)),
      "orders": bucket["orders"],
    })

  return {
    "period_days": days,
    "group_by": group_by,
    "orders_compared": summary["orders_compared"],
    "orders_without_competition": summary["orders_without_competition"],
    "total_savings": summary["total_savings"],
    "savings_pct": summary["savings_pct"],
    "points": points,
  }
