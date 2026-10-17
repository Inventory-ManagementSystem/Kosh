from celery import shared_task
from django.utils import timezone

from accounts.models import Business

from .alert_services import create_alerts_for_business
from .models import RFQ, ReorderSuggestion
from .rfq_services import RFQCreationError, create_rfq_for_suggestion


@shared_task
def check_low_stock():
  created = 0
  for business in Business.objects.iterator():
    created += create_alerts_for_business(business)
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
