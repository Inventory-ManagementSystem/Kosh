from celery import shared_task
from django.utils import timezone

from accounts.models import Business

from .alert_services import create_alerts_for_business
from .models import RFQ, ReorderSuggestion
from .rfq_services import RFQCreationError, create_rfqs_for_suggestions


@shared_task
def check_low_stock():
  created = 0
  for business in Business.objects.iterator():
    created += create_alerts_for_business(business)
  return created

@shared_task
def create_auto_rfqs():
  alerts = (
    ReorderSuggestion.objects.filter(
      status=ReorderSuggestion.Status.OPEN,
      method="formula",
      suggested_quantity__gte=1,
      product__supply_category__isnull=False,
    )
    .select_related("business", "product")
    .order_by("created_at")
  )

  groups = {}
  for alert in alerts.iterator():
    key = (alert.business_id, alert.product.supply_category_id)
    group = groups.setdefault(key, {"business": alert.business, "alerts": []})
    group["alerts"].append((alert.pk, None))

  created = 0
  for group in groups.values():
    try:
      created += len(create_rfqs_for_suggestions(group["business"], group["alerts"]))
    except RFQCreationError:
      continue
  return created


@shared_task
def close_expired_rfqs():
  now = timezone.now()
  return RFQ.objects.filter(status=RFQ.Status.OPEN, deadline__lte=now).update(
    status=RFQ.Status.CLOSED, updated_at=now
  )
