from datetime import timedelta

from celery import shared_task
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Business
from inventory.models import Product
from inventory.reorder import calculate_reorder, get_dispatch_stats
from notifications import events
from .models import RFQ, ReorderSuggestion

REMINDER_HOURS = 6  


@shared_task
def check_low_stock():
  created = 0
  for business in Business.objects.iterator():
    stats = get_dispatch_stats(business)
    active = set(
      ReorderSuggestion.objects.filter(
        business=business, status__in=ReorderSuggestion.ACTIVE
      ).values_list("product_id", flat=True)
    )

    new_low = []
    for product in Product.objects.filter(business=business, is_active=True).iterator():
      if product.id in active:
        continue
      result = calculate_reorder(product, stats)
      if not result.needs_reorder:
        continue
      try:
        with transaction.atomic():
          ReorderSuggestion.objects.create(
            business=business,
            product=product,
            method=result.method,
            stock_at_creation=product.quantity,
            reorder_point=result.reorder_point,
            avg_daily_dispatch=result.avg_daily,
            suggested_quantity=result.suggested_quantity,
          )
        created += 1
        new_low.append(product)
      except IntegrityError:
        pass
    events.low_stock_alerts(business, new_low)
  return created


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