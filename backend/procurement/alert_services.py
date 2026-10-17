from django.db import IntegrityError, transaction

from inventory.models import Product
from inventory.reorder import calculate_reorder, get_dispatch_stats

from .models import ReorderSuggestion


def create_alerts_for_business(business):
  
  stats = get_dispatch_stats(business)
  active = set(
    ReorderSuggestion.objects.filter(
      business=business, status__in=ReorderSuggestion.ACTIVE
    ).values_list("product_id", flat=True)
  )

  created = 0
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
