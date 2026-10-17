
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


def find_recipients(business, supply_category, include_platform_pool=False):

  recipients = {}

  own = Supplier.objects.filter(
    business=business,
    is_active=True,
    linked_account__is_verified=True,
    linked_account__categories=supply_category,
  ).select_related("linked_account__user")
  for record in own:
    recipients[record.linked_account_id] = (
      record.linked_account, RFQRecipient.Source.OWN, record
    )

  if include_platform_pool:
    pool = SupplierProfile.objects.filter(
      is_verified=True,
      city__iexact=business.city,
      categories=supply_category,
    ).select_related("user")
    for profile in pool:
      recipients.setdefault(profile.pk, (profile, RFQRecipient.Source.PLATFORM, None))

  return recipients


@transaction.atomic
def create_rfqs_for_suggestions(
  business, selections, include_platform_pool=False, created_by=None
):
  quantities = dict(selections)
  suggestions = list(
    ReorderSuggestion.objects.select_for_update(of=("self",))
    .select_related("product__supply_category")
    .filter(business=business, pk__in=list(quantities))
    .order_by("pk")
  )
  if len(suggestions) != len(quantities):
    raise RFQCreationError("One or more selected alerts were not found.", "ALERT_NOT_FOUND")

  groups = {}
  for s in suggestions:
    product = s.product
    if s.status != ReorderSuggestion.Status.OPEN:
      raise RFQCreationError(
        f"The alert for {product.name} already has an RFQ or is closed.",
        "SUGGESTION_NOT_OPEN",
      )
    if product.supply_category_id is None:
      raise RFQCreationError(
        f"Set a supply category on {product.name} so we know which suppliers to ask.",
        "NO_SUPPLY_CATEGORY",
      )
    qty = quantities[s.pk] if quantities[s.pk] is not None else s.suggested_quantity
    if qty < 1:
      raise RFQCreationError("Quantity must be at least 1.", "INVALID_QUANTITY")
    group = groups.setdefault(
      product.supply_category_id,
      {"category": product.supply_category, "rows": []},
    )
    group["rows"].append((s, qty))

  for group in groups.values():
    group["recipients"] = find_recipients(
      business, group["category"], include_platform_pool
    )
    if not group["recipients"]:
      raise RFQCreationError(
        f"No verified suppliers found for {group['category'].name}.", "NO_SUPPLIERS"
      )

  Business.objects.select_for_update().get(pk=business.pk)
  deadline = timezone.now() + timedelta(days=RFQ_DEADLINE_DAYS)
  return [
    _create_group_rfq(business, group, include_platform_pool, created_by, deadline)
    for group in sorted(groups.values(), key=lambda g: g["category"].name)
  ]

def _create_group_rfq(business, group, include_platform_pool, created_by, deadline):
  category = group["category"]
  rows = group["rows"]
  recipients = group["recipients"]

  rfq = RFQ.objects.create(
    business=business,
    number=next_rfq_number(business),
    supply_category=category,
    include_platform_pool=include_platform_pool,
    deadline=deadline,
    created_by=created_by,
  )
  RFQItem.objects.bulk_create([
    RFQItem(
      rfq=rfq, product=s.product, product_name=s.product.name,
      sku=s.product.sku, quantity=qty,
    )
    for s, qty in rows
  ])
  RFQRecipient.objects.bulk_create([
    RFQRecipient(rfq=rfq, supplier_profile=profile, supplier=record, source=source)
    for profile, source, record in recipients.values()
  ])
  ReorderSuggestion.objects.filter(pk__in=[s.pk for s, _ in rows]).update(
    rfq=rfq,
    status=ReorderSuggestion.Status.RFQ_CREATED,
    updated_at=timezone.now(),
  )

  if len(rows) == 1:
    s, qty = rows[0]
    need = f"{business.business_name} needs {qty} x {s.product.name}."
  else:
    need = f"{business.business_name} needs {len(rows)} products ({category.name})."
  notify_many(
    [profile.user for profile, _, _ in recipients.values()],
    f"New RFQ {rfq.number}",
    f"{need} Send your quotation before {rfq.deadline:%d %b %Y}.",
    kind=Notification.Kind.RFQ,
  )
  if created_by is None:
    notify(
      business.owner,
      f"RFQ {rfq.number} created automatically",
      f"{len(rows)} {category.name} product(s) are running low. "
      f"The RFQ was sent to {len(recipients)} supplier(s).",
      kind=Notification.Kind.RFQ,
      push=False,
    )

  return rfq

def create_rfq_for_suggestion(
  suggestion, quantity=None, include_platform_pool=False, created_by=None
):
  rfqs = create_rfqs_for_suggestions(
    suggestion.business,
    [(suggestion.pk, quantity)],
    include_platform_pool=include_platform_pool,
    created_by=created_by,
  )
  return rfqs[0]


