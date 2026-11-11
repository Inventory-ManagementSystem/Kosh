from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .models import PurchaseOrder, Quotation

CENT = Decimal("0.01")
TENTH = Decimal("0.1")
ZERO = Decimal("0")
DEFAULT_DAYS = 90
MAX_DAYS = 365

COMPETING = (Quotation.Status.SUBMITTED, Quotation.Status.REJECTED)

def _money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def _pct(part, whole):
    if whole <= 0:
        return 0.0
    return float((part/whole*100).quantize(TENTH, rounding=ROUND_HALF_UP))

def savings_summary(business, days=DEFAULT_DAYS):
    since = timezone.now() - timedelta(days=days)
    orders = list(
        PurchaseOrder.objects.filter(
            business = business,
            status__in = PurchaseOrder.SUPPLIER_VISIBLE,
            created_at__gte = since,
        )
        .select_related("supplier_profile", "rfq")
        .order_by("-created_at")
    )

    competing = defaultdict(lambda: {"count": 0, "total": ZERO})
    if orders:
        rows = (
            Quotation.objects.filter(
                rfq_id__in={po.rfq_id for po in orders}, status__in=COMPETING
            )
            .exclude(pk__in={po.quotation_id for po in orders})
            .values_list("rfq_id", "grand_total")
        )
        for rfq_id, grand_total in rows:
            competing[rfq_id]["count"] += 1
            competing[rfq_id]["total"] +=grand_total

    results = []
    net = ZERO
    benchmark = ZERO
    skipped=0
    for po in orders:
        group = competing.get(po.rfq_id)
        if group is None:
            skipped +=1
            continue
        average = _money(group["total"]/group["count"])
        saving=average - po.grand_total
        net+=saving
        benchmark+=average
        results.append({
            "order_id": po.id,
            "order_number": po.number,
            "rfq_number": po.rfq.number,
            "supplier_name": po.supplier_profile.company_name,
            "ordered_at": po.created_at,
            "order_total": str(po.grand_total),
            "competing_quotes": group["count"],
            "average_competing_total": str(average),
            "savings": str(saving),
            "savings_pct": _pct(saving, average)
        })

    return{
        "period_days": days,
        "orders_compared": len(results),
        "orders_without_competition": skipped,
        "total_savings": str(_money(net)),
        "savings_pct": _pct(net, benchmark),
        "orders": results,
    }
