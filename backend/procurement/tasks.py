from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from accounts.models import Business
from notifications import events

from .alert_services import create_alerts_for_business
from .models import RFQ, ReorderSuggestion
from .rfq_services import RFQCreationError, create_rfqs_for_suggestions

REMINDER_HOURS = 6


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


def _open_rfqs_with_deadline_between(start, end):
  return (
    RFQ.objects.filter(status=RFQ.Status.OPEN, deadline__gt=start, deadline__lte=end)
    .select_related("business__owner")
    .prefetch_related("items")
  )


@shared_task
def send_rfq_deadline_reminders():
  now = timezone.now()
  start = now + timedelta(hours=REMINDER_HOURS - 1)
  end = now + timedelta(hours=REMINDER_HOURS)
  rfqs = list(_open_rfqs_with_deadline_between(start, end))
  for rfq in rfqs:
    events.rfq_deadline_reminder(rfq, REMINDER_HOURS)
  return len(rfqs)


@shared_task
def notify_rfq_deadlines_passed():
  now = timezone.now()
  rfqs = list(_open_rfqs_with_deadline_between(now - timedelta(hours=1), now))
  for rfq in rfqs:
    events.rfq_quotes_ready(rfq)
  return len(rfqs)
