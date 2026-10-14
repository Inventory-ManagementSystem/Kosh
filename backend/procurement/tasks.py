from celery import shared_task
from django.db import IntegrityError, transaction

from accounts.models import Business
from inventory.models import Product
from inventory.reorder import calculate_reorder, get_dispatch_stats

from .models import RFQ, ReorderSuggestion
from django.utils import timezone
from .rfq_services import RFQCreationError, create_rfq_for_suggestion

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
      except IntegrityError:
        pass
  return created

@shared_task
def create_auto_rfqs():
  created = 0
  suggestions = ReorderSuggestion.objects.filter(
    status=ReorderSuggestion.Status.OPEN, method="formula"
  )
  for suggestion in suggestions.iterator():
    try:
      create_rfq_for_suggestion(suggestion)
      created += 1
    except RFQCreationError:
      continue
  return created


@shared_task
def close_expired_rfqs():
  now = timezone.now()
  return RFQ.objects.filter(status=RFQ.Status.OPEN, deadline__lte=now).update(
    status=RFQ.Status.CLOSED, updated_at=now
  )
