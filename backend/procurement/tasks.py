from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from accounts.models import Business
from notifications import events

from .alert_services import create_alerts_for_business

import logging

from .models import RFQ, ReorderSuggestion, PurchaseOrder
from .po_services import expire_unpaid_order
from .rfq_services import RFQCreationError, create_rfqs_for_suggestions

logger = logging.getLogger(__name__)

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


def _hour_start():
  return timezone.now().astimezone(events.IST).replace(minute=0, second=0, microsecond=0)


def _rfqs_with_deadline_between(start, end, statuses):
  return (
    RFQ.objects.filter(status__in=statuses, deadline__gt=start, deadline__lte=end)
    .select_related("business__owner")
    .prefetch_related("items")
  )


@shared_task
def send_rfq_deadline_reminders():
  now = _hour_start()
  start = now + timedelta(hours=REMINDER_HOURS - 1)
  end = now + timedelta(hours=REMINDER_HOURS)
  rfqs = list(_rfqs_with_deadline_between(start, end, [RFQ.Status.OPEN]))
  for rfq in rfqs:
    events.rfq_deadline_reminder(rfq, REMINDER_HOURS)
  return len(rfqs)


@shared_task
def notify_rfq_deadlines_passed():
  now = _hour_start()
  rfqs = list(_rfqs_with_deadline_between(
    now - timedelta(hours=1), now, [RFQ.Status.OPEN, RFQ.Status.CLOSED]
  ))
  for rfq in rfqs:
    events.rfq_quotes_ready(rfq)
  return len(rfqs)

@shared_task
def cancel_expired_unpaid_orders():
  ids = list(
    PurchaseOrder.objects.filter(
      status=PurchaseOrder.Status.AWAITING_ADVANCE,
      advance_due_by__lte=timezone.now(),
    ).values_list("pk", flat=True)
  )
  cancelled = 0
  for po_id in ids:
    try:
      if expire_unpaid_order(po_id):
        cancelled += 1
    except Exception:
      logger.exception("Could not expire order %s", po_id)
  return cancelled
