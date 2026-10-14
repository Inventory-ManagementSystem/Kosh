from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import (
  Count, DecimalField, F, Max, Q, Sum, Value,
)
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from inventory.models import DispatchItem, DispatchNote, Outlet, Product, StockMovement
from inventory.reorder import calculate_reorder, get_dispatch_stats

IST = ZoneInfo("Asia/Kolkata")

MONEY_FIELD = DecimalField(max_digits=18, decimal_places=2)
ZERO = Value(Decimal("0"), output_field=MONEY_FIELD)

Reason = StockMovement.Reason


def money(value):
  return float(round(value or Decimal("0"), 2))


def window(days):
  today = timezone.localdate(timezone=IST)
  start_date = today - timedelta(days=days - 1)
  return start_date, datetime.combine(start_date, time.min, tzinfo=IST)


def active_products(business):
  return Product.objects.filter(business=business, is_active=True)


def _stock_value(field):
  return Coalesce(Sum(F("quantity") * F(field), output_field=MONEY_FIELD), ZERO)


def overview(business, days):
  start_date, since = window(days)
  products = active_products(business)

  stock = products.aggregate(
    total_products=Count("id"),
    total_units=Coalesce(Sum("quantity"), 0),
    value_at_cost=_stock_value("cost_price"),
    value_at_price=_stock_value("price"),
    missing_cost_price=Count("id", filter=Q(cost_price__isnull=True)),
    out_of_stock=Count("id", filter=Q(quantity=0)),
    low_stock=Count(
      "id", filter=Q(quantity__gt=0, quantity__lte=F("low_stock_threshold"))
    ),
  )

  moves = StockMovement.objects.filter(business=business, created_at__gte=since)
  flow = moves.aggregate(
    units_in=Coalesce(Sum(
      "quantity_change",
      filter=Q(quantity_change__gt=0) & ~Q(reason=Reason.OPENING_BALANCE),
    ), 0),
    units_dispatched=Coalesce(Sum(
      "quantity_change", filter=Q(reason=Reason.DISPATCH)
    ), 0),
    units_damaged=Coalesce(Sum(
      "quantity_change", filter=Q(reason=Reason.DAMAGED)
    ), 0),
    damaged_value=Coalesce(Sum(
      -F("quantity_change") * F("product__cost_price"),
      filter=Q(reason=Reason.DAMAGED),
      output_field=MONEY_FIELD,
    ), ZERO),
  )

  return {
    "period_days": days,
    "period_start": start_date,
    "stock": {
      "total_products": stock["total_products"],
      "total_units": stock["total_units"],
      "value_at_cost": money(stock["value_at_cost"]),
      "value_at_price": money(stock["value_at_price"]),
      "products_missing_cost_price": stock["missing_cost_price"],
      "low_stock": stock["low_stock"],
      "out_of_stock": stock["out_of_stock"],
    },
    "period": {
      "units_received": flow["units_in"],
      "units_dispatched": abs(flow["units_dispatched"]),
      "units_damaged": abs(flow["units_damaged"]),
      "damaged_value": money(flow["damaged_value"]),
      "dispatch_notes": DispatchNote.objects.filter(
        business=business, dispatch_date__gte=start_date
      ).count(),
    },
    "active_outlets": Outlet.objects.filter(business=business, is_active=True).count(),
  }


def stock_breakdown(business):
  products = active_products(business)

  status = products.aggregate(
    in_stock=Count("id", filter=Q(quantity__gt=F("low_stock_threshold"))),
    low_stock=Count(
      "id", filter=Q(quantity__gt=0, quantity__lte=F("low_stock_threshold"))
    ),
    out_of_stock=Count("id", filter=Q(quantity=0)),
  )

  rows = (
    products.values("category_id", "category__name")
    .annotate(
      products=Count("id"),
      units=Coalesce(Sum("quantity"), 0),
      value_at_cost=_stock_value("cost_price"),
      value_at_price=_stock_value("price"),
    )
    .order_by("-value_at_cost")
  )
  categories = [
    {
      "category_id": r["category_id"],
      "category": r["category__name"] or "Uncategorized",
      "products": r["products"],
      "units": r["units"],
      "value_at_cost": money(r["value_at_cost"]),
      "value_at_price": money(r["value_at_price"]),
    }
    for r in rows
  ]
  return {"status": status, "categories": categories}



def movement_trend(business, days):
  start_date, since = window(days)
  rows = (
    StockMovement.objects.filter(business=business, created_at__gte=since)
    .exclude(reason=Reason.OPENING_BALANCE)
    .annotate(day=TruncDate("created_at", tzinfo=IST))
    .values("day")
    .annotate(
      stock_in=Coalesce(Sum("quantity_change", filter=Q(quantity_change__gt=0)), 0),
      dispatched=Coalesce(Sum("quantity_change", filter=Q(reason=Reason.DISPATCH)), 0),
      damaged=Coalesce(Sum("quantity_change", filter=Q(reason=Reason.DAMAGED)), 0),
      adjusted_out=Coalesce(Sum(
        "quantity_change",
        filter=Q(reason=Reason.ADJUSTMENT, quantity_change__lt=0),
      ), 0),
    )
  )
  by_day = {r["day"]: r for r in rows}

  series = []
  for i in range(days): 
    day = start_date + timedelta(days=i)
    r = by_day.get(day, {})
    series.append({
      "date": day,
      "stock_in": r.get("stock_in", 0),
      "dispatched": abs(r.get("dispatched", 0)),
      "damaged": abs(r.get("damaged", 0)),
      "adjusted_out": abs(r.get("adjusted_out", 0)),
    })
  return {"period_days": days, "series": series}


def top_products(business, days, limit):
  _, since = window(days)
  rows = (
    StockMovement.objects.filter(
      business=business, reason=Reason.DISPATCH, created_at__gte=since
    )
    .values("product_id", "product__name", "product__sku", "product__quantity")
    .annotate(
      units=Sum("quantity_change"),
      value=Sum(-F("quantity_change") * F("product__price"), output_field=MONEY_FIELD),
    )
    .order_by("units") 
    [:limit]
  )
  return [
    {
      "product_id": r["product_id"],
      "name": r["product__name"],
      "sku": r["product__sku"],
      "units_dispatched": abs(r["units"]),
      "dispatch_value": money(r["value"]),
      "current_stock": r["product__quantity"],
    }
    for r in rows
  ]



def slow_moving(business, days, limit):
  _, since = window(days)
  qs = (
    active_products(business)
    .filter(quantity__gt=0, created_at__lt=since)
    .annotate(
      last_dispatch=Max(
        "movements__created_at", filter=Q(movements__reason=Reason.DISPATCH)
      ),
      tied_value=Coalesce(
        F("quantity") * F("cost_price"), ZERO, output_field=MONEY_FIELD
      ),
    )
    .filter(Q(last_dispatch__lt=since) | Q(last_dispatch__isnull=True))
  )
  totals = qs.aggregate(
    count=Count("id"),
    units=Coalesce(Sum("quantity"), 0),
    value=Coalesce(Sum("tied_value"), ZERO),
  )
  items = qs.select_related("category").order_by("-tied_value", "name")[:limit]

  return {
    "no_dispatch_days": days,
    "count": totals["count"],
    "units": totals["units"],
    "value_at_cost": money(totals["value"]),
    "items": [
      {
        "product_id": p.id,
        "name": p.name,
        "sku": p.sku,
        "category": p.category.name if p.category else None,
        "quantity": p.quantity,
        "value_at_cost": money(p.tied_value),
        "last_dispatched_at": p.last_dispatch,
      }
      for p in items
    ],
  }



def stock_cover(business, limit):
  stats = get_dispatch_stats(business)
  rows = []
  for p in active_products(business).only(
    "id", "name", "sku", "quantity", "low_stock_threshold",
    "lead_time_days", "safety_stock", "reorder_quantity",
  ):
    result = calculate_reorder(p, stats)
    if result.avg_daily <= 0:
      continue
    cover = round(p.quantity / result.avg_daily, 1)
    rows.append({
      "product_id": p.id,
      "name": p.name,
      "sku": p.sku,
      "quantity": p.quantity,
      "avg_daily_dispatch": result.avg_daily,
      "days_of_cover": cover,
      "lead_time_days": p.lead_time_days,
      "at_risk": cover <= p.lead_time_days,
    })
  rows.sort(key=lambda r: r["days_of_cover"])
  return {
    "at_risk_count": sum(r["at_risk"] for r in rows),
    "items": rows[:limit],
  }


def outlet_dispatch(business, days):
  start_date, _ = window(days)
  rows = (
    DispatchItem.objects.filter(
      dispatch_note__business=business,
      dispatch_note__dispatch_date__gte=start_date,
    )
    .values("dispatch_note__outlet_id", "dispatch_note__outlet__name")
    .annotate(
      units=Sum("quantity"),
      value=Sum(F("quantity") * F("product__price"), output_field=MONEY_FIELD),
      dispatches=Count("dispatch_note", distinct=True),
    )
    .order_by("-units")
  )
  return [
    {
      "outlet_id": r["dispatch_note__outlet_id"],
      "outlet": r["dispatch_note__outlet__name"],
      "dispatches": r["dispatches"],
      "units": r["units"],
      "value": money(r["value"]),
    }
    for r in rows
  ]