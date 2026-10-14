
import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import Business
from suppliers.models import Supplier, SupplierProfile

from .models import RFQ, RFQItem, RFQRecipient, ReorderSuggestion

from notifications.models import Notification
from notifications.services import notify, notify_many

RFQ_DEADLINE_DAYS = 3


class RFQCreationError(Exception):
  def __init__(self, message, code):
    super().__init__(message)
    self.message = message
    self.code = code


def next_rfq_number(business):
  numbers = RFQ.objects.filter(
    business=business, number__regex=r"^RFQ-[0-9]+$"
  ).values_list("number", flat=True)
  highest = max((int(n.split("-")[1]) for n in numbers), default=0)
  return f"RFQ-{highest + 1:04d}"


def find_recipients(business, product, include_platform_pool=False):
  recipients = {}

  own = Supplier.objects.filter(
    business=business, is_active=True, linked_account__is_verified=True
  ).select_related("linked_account__user")
  for record in own:
    recipients[record.linked_account_id] = (
      record.linked_account, RFQRecipient.Source.OWN, record
    )

  if include_platform_pool:
    pool = SupplierProfile.objects.filter(
      is_verified=True, city__iexact=business.city
    ).select_related("user")
    if product.category_id:
      pool = pool.filter(
        categories__is_active=True,
        categories__name__iexact=product.category.name,
      )
    for profile in pool.distinct():
      recipients.setdefault(profile.pk, (profile, RFQRecipient.Source.PLATFORM, None))

  return recipients


@transaction.atomic
def create_rfq_for_suggestion(
  suggestion, quantity=None, include_platform_pool=False, created_by=None
):
  suggestion = (
    ReorderSuggestion.objects.select_for_update(of=("self",))
    .select_related("product__category", "business")
    .get(pk=suggestion.pk)
  )
  if suggestion.status != ReorderSuggestion.Status.OPEN:
    raise RFQCreationError("This alert already has an RFQ or is closed.", "SUGGESTION_NOT_OPEN")

  business = suggestion.business
  product = suggestion.product

  qty = quantity if quantity is not None else suggestion.suggested_quantity
  if qty < 1:
    raise RFQCreationError("Quantity must be at least 1.", "INVALID_QUANTITY")

  recipients = find_recipients(business, product, include_platform_pool)
  if not recipients:
    raise RFQCreationError(
      "No verified suppliers to send this RFQ to.", "NO_SUPPLIERS"
    )

  Business.objects.select_for_update().get(pk=business.pk)

  rfq = RFQ.objects.create(
    business=business,
    number=next_rfq_number(business),
    reorder_suggestion=suggestion,
    include_platform_pool=include_platform_pool,
    deadline=timezone.now() + timedelta(days=RFQ_DEADLINE_DAYS),
    created_by=created_by,
  )
  RFQItem.objects.create(
    rfq=rfq, product=product, product_name=product.name, sku=product.sku, quantity=qty
  )
  RFQRecipient.objects.bulk_create([
    RFQRecipient(rfq=rfq, supplier_profile=profile, supplier=record, source=source)
    for profile, source, record in recipients.values()
  ])

  suggestion.status = ReorderSuggestion.Status.RFQ_CREATED
  suggestion.save(update_fields=["status", "updated_at"])

  notify_many(
    [profile.user for profile, _, _ in recipients.values()],
    f"New RFQ {rfq.number}",
    f"{business.business_name} needs {qty} x {product.name}. "
    f"Send your quotation before {rfq.deadline:%d %b %Y}.",
    kind=Notification.Kind.RFQ,
  )
  if created_by is None:
    notify(
      business.owner,
      f"RFQ {rfq.number} created automatically",
      f"{product.name} is running low. The RFQ was sent to {len(recipients)} supplier(s).",
      kind=Notification.Kind.RFQ,
      push=False,
    )
  
  return rfq
