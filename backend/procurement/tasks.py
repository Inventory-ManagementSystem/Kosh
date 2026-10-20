from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from accounts.models import Business
from notifications import events

from .alert_services import create_alerts_for_business
from .models import RFQ, ReorderSuggestion, PurchaseOrder
from .rfq_services import RFQCreationError, create_rfqs_for_suggestions
import logging
from .payment_services import PaymentError, expire_advance, refund_payment

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
def expire_unpaid_advances():
  due = list(
    PurchaseOrder.objects.filter(
      status=PurchaseOrder.Status.AWAITING_ADVANCE,
      advance_due_by__lte=timezone.now(),
    ).values_list("pk", flat=True)
  )
  cancelled = 0
  for po_id in due:
    try:
      cancelled += int(expire_advance(po_id))
    except Exception:
      logger.exception("Couldn't expire advance for PO %s", po_id)
  return cancelled


@shared_task(bind=True, max_retries=6, default_retry_delay=600)
def refund_advance_payment(self, payment_pk):
  try:
    return refund_payment(payment_pk)
  except PaymentError as err:
    raise self.retry(exc=err)
