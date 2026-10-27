from django.db import IntegrityError, transaction

from inventory.models import Product
from inventory.reorder import calculate_reorder, get_dispatch_stats
from notifications import events
from django.utils import timezone

from .models import (
  PurchaseOrder, PurchaseOrderItem, ReorderSuggestion, RFQ, RFQItem,
)

def _on_order_product_ids(business, product_ids=None):
  rfq_items = RFQItem.objects.filter(
    rfq__business=business,
    rfq__status__in=[RFQ.Status.OPEN, RFQ.Status.CLOSED],
  )
  po_items = PurchaseOrderItem.objects.filter(
    purchase_order__business=business,
    purchase_order__status__in=[
      PurchaseOrder.Status.AWAITING_ADVANCE,
      PurchaseOrder.Status.ISSUED,
      PurchaseOrder.Status.DISPATCHED,
      PurchaseOrder.Status.PARTIALLY_RECEIVED,
    ],
  )
  if product_ids is not None:
    rfq_items = rfq_items.filter(product_id__in=product_ids)
    po_items = po_items.filter(product_id__in=product_ids)
  return set(rfq_items.values_list("product_id", flat=True)) | set(
    po_items.values_list("product_id", flat=True)
  )

import logging
logger = logging.getLogger(__name__)


def create_alerts_for_business(business, notify=True, product_ids=None):
  stats = get_dispatch_stats(business)
  active = set(
    ReorderSuggestion.objects.filter(
      business=business, status__in=ReorderSuggestion.ACTIVE
    ).values_list("product_id", flat=True)
  )

  active |= _on_order_product_ids(business, product_ids)
  created = 0
  new_low = []
  products = Product.objects.filter(business=business, is_active=True)
  if product_ids is not None:
    products = products.filter(pk__in=product_ids)
  for product in products.iterator():
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

  if notify:
    events.low_stock_alerts(business, new_low)
  return created


def check_low_stock_on_commit(business, product_ids):
  product_ids = list(product_ids)

  def run():
    try:
      create_alerts_for_business(business, product_ids=product_ids)
    except Exception:
      logger.exception("Low-stock check failed for business %s", business.pk)

  transaction.on_commit(run)

def close_active_alerts(product_ids):
  ReorderSuggestion.objects.filter(
    product_id__in=product_ids, status__in=ReorderSuggestion.ACTIVE
  ).update(status=ReorderSuggestion.Status.CLOSED, updated_at=timezone.now())
