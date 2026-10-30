import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from accounts.models import Business
from notifications import events

from django.db.models import Q
from .alert_services import create_alerts_for_business, close_recovered_alerts
from .models import RFQ, PurchaseOrder, ReorderSuggestion, Payout
from .payment_services import PaymentError, expire_advance, refund_payment, send_owner_refund
from .rfq_services import RFQCreationError, create_rfqs_for_suggestions
from .preferences import get_procurement_settings
from .payout_services import PayoutError, send_payout, sync_payout
logger = logging.getLogger(__name__)

REMINDER_HOURS = 6
STUCK_GRACE_DAYS=2
STUCK_REMINDER_DAYS=3


@shared_task
def check_low_stock():
  created = 0
  for business in Business.objects.iterator():
    try:
      close_recovered_alerts(business)
    except Exception:
      logger.exception("Closing stale alerts failed for business %s", business.pk)
    try:
      created += create_alerts_for_business(business)
    except Exception:
      logger.exception("Low-stock check failed for business %s", business.pk)
  return created


@shared_task
def create_auto_rfqs():
  alerts = (
    ReorderSuggestion.objects.filter(
      status=ReorderSuggestion.Status.OPEN,
      suggested_quantity__gte=1,
      product__supply_category__isnull=False,
    )
    .select_related("business", "product")
    .order_by("created_at")
  )

  prefs_by_business = {}
  groups = {}
  for alert in alerts:
    prefs = prefs_by_business.get(alert.business_id)
    if prefs is None:
      prefs = get_procurement_settings(alert.business)
      prefs_by_business[alert.business_id] = prefs
    if alert.method != "formula" and not prefs.auto_rfq_include_manual:
      continue
    key = (alert.business_id, alert.product.supply_category_id)
    group = groups.setdefault(
      key, {"business": alert.business, "prefs": prefs, "alerts": []}
    )
    group["alerts"].append((alert.pk, None))

  created = 0 
  for group in groups.values():
    try:
      created += len(create_rfqs_for_suggestions(
        group["business"],
        group["alerts"],
        include_platform_pool=group["prefs"].auto_rfq_include_platform_pool,
      ))
    except RFQCreationError as err:
      logger.warning(
        "Auto RFQ skipped for business %s: %s (%s)",
        group["business"].pk, err.message, err.code,
      )
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
      if expire_advance(po_id):
        cancelled += 1
    except Exception:
      logger.exception("Could not expire order %s", po_id)
  return cancelled


@shared_task(bind=True, max_retries=6, default_retry_delay=600)
def refund_advance_payment(self, payment_pk):
  try:
    return refund_payment(payment_pk)
  except PaymentError as err:
    raise self.retry(exc=err)

@shared_task(bind=True, max_retries=5, default_retry_delay=120)
def send_advance_payout(self, payout_pk):
  try:
    send_payout(payout_pk)
  except PayoutError as err:
    raise self.retry(exc=err)


@shared_task
def sync_payouts():
  now = timezone.now()
  stuck = Payout.objects.filter(
    status=Payout.Status.PENDING, updated_at__lte=now - timedelta(minutes=10)
  ).values_list("pk", flat=True)
  for payout_pk in list(stuck):
    send_advance_payout.delay(str(payout_pk))

  in_flight = Payout.objects.filter(
    status=Payout.Status.PROCESSING, updated_at__lte=now - timedelta(minutes=30)
  ).values_list("pk", flat=True)
  synced = 0
  for payout_pk in list(in_flight):
    try:
      sync_payout(payout_pk)
      synced += 1
    except Exception:
      logger.exception("Couldn't sync payout %s", payout_pk)
  return synced


@shared_task(bind=True, max_retries=6, default_retry_delay=600)
def refund_owner(self, refund_pk):
  try:
    return str(send_owner_refund(refund_pk).status)
  except PaymentError as err:
    raise self.retry(exc=err)

@shared_task
def notify_stuck_orders():
  now = timezone.now()
  today = timezone.localdate()
  grace_date = today - timedelta(days=STUCK_GRACE_DAYS)
  not_recent = Q(stuck_notified_at__isnull=True) | Q(
    stuck_notified_at__lte=now - timedelta(days=STUCK_REMINDER_DAYS)
  )

  not_dispatched = PurchaseOrder.objects.filter(
    not_recent,
    status=PurchaseOrder.Status.ISSUED,
    delivery_date__lt=grace_date,
  ).select_related("business__owner", "supplier_profile")

  not_received = PurchaseOrder.objects.filter(
    not_recent,
    status=PurchaseOrder.Status.DISPATCHED,
    shipment__expected_delivery_date__lt=grace_date,
    shipment__dispatched_at__lt=now - timedelta(days=STUCK_GRACE_DAYS),
  ).select_related("business__owner", "supplier_profile", "shipment")

  sent = 0
  for po in list(not_dispatched):
    try:
      events.po_dispatch_overdue(po, (today - po.delivery_date).days)
    except Exception:
      logger.exception("Overdue notice failed for order %s", po.pk)
      continue
    PurchaseOrder.objects.filter(pk=po.pk).update(stuck_notified_at=now)
    sent += 1

  for po in list(not_received):
    try:
      events.po_receipt_overdue(po, (today - po.shipment.expected_delivery_date).days)
    except Exception:
      logger.exception("Overdue notice failed for order %s", po.pk)
      continue
    PurchaseOrder.objects.filter(pk=po.pk).update(stuck_notified_at=now)
    sent += 1
  return sent
