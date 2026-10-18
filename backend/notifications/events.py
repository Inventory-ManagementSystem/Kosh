import functools
import logging
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import Notification
from .services import notify, notify_many

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
Kind = Notification.Kind


def safe(func):
  @functools.wraps(func)
  def wrapper(*args, **kwargs):
    try:
      with transaction.atomic():
        return func(*args, **kwargs)
    except Exception:
      logger.exception("Notification %s failed", func.__name__)
      return None
  return wrapper


def display_name(user):
  name = getattr(getattr(user, "profile", None), "name", "") or ""
  return name or user.email or user.username


def rupees(amount):
  return f"₹{amount}"


def when(dt):
  return dt.astimezone(IST).strftime("%d %b, %I:%M %p")


def items_label(rfq):
  items = list(rfq.items.all())
  if not items:
    return "items"
  if len(items) == 1:
    return items[0].product_name
  category = f" ({rfq.supply_category.name})" if rfq.supply_category_id else ""
  return f"{len(items)} products{category}"


def supplier_users(rfq, exclude_declined=True):
  recipients = rfq.recipients.select_related("supplier_profile__user")
  if exclude_declined:
    recipients = recipients.exclude(status="declined")
  return [r.supplier_profile.user for r in recipients]


def list_names(names, limit=3):
  names = list(names)
  shown = ", ".join(names[:limit])
  more = len(names) - limit
  return f"{shown} and {more} more" if more > 0 else shown


@safe
def low_stock_alerts(business, products):
  products = list(products)
  if not products:
    return
  if len(products) == 1:
    title = f"{products[0].name} is low on stock"
    body = f"Only {products[0].quantity} left. Create an RFQ to restock."
  else:
    title = f"{len(products)} products are low on stock"
    body = f"{list_names(p.name for p in products)}. Create RFQs to restock."
  notify(business.owner, title, body, kind=Kind.LOW_STOCK)


@safe
def rfq_cancelled(rfq):
  notify_many(
    supplier_users(rfq),
    f"{rfq.number} was cancelled",
    f"{rfq.business.business_name} cancelled this request for {items_label(rfq)}. "
    "No quotation is needed.",
    kind=Kind.RFQ,
  )


@safe
def rfq_updated(rfq, changed_fields):
  users = supplier_users(rfq)
  if "deadline" in changed_fields:
    notify_many(
      users,
      f"New deadline for {rfq.number}",
      f"{rfq.business.business_name} changed the deadline. Quote by {when(rfq.deadline)}.",
      kind=Kind.RFQ,
    )
  elif "notes" in changed_fields:
    notify_many(
      users,
      f"{rfq.number} was updated",
      f"{rfq.business.business_name} updated the notes on this request.",
      kind=Kind.RFQ,
      push=False,
    )


@safe
def supplier_verified(profile):
  notify(
    profile.user,
    "Your supplier account is verified",
    "You can now receive requests for quotation from businesses on Kosh.",
  )


@safe
def supplier_unverified(profile):
  notify(
    profile.user,
    "Your supplier account needs verification again",
    "An admin will review your details. You won't receive new platform RFQs until then.",
  )


@safe
def supplier_added(supplier):
  if not supplier.linked_account_id:
    return 
  notify(
    supplier.linked_account.user,
    f"{supplier.business.business_name} added you as a supplier",
    "You'll get their requests for quotation here.",
  )


@safe
def employee_invited(invite):
  user = User.objects.filter(email__iexact=invite.email).first()
  if user is None:
    return  
  notify(
    user,
    f"{invite.business.business_name} invited you to their team",
    "Open your invites to accept or decline.",
  )


@safe
def invite_accepted(business, employee_user):
  notify(
    business.owner,
    f"{display_name(employee_user)} joined your team",
    "They can now use Kosh as an employee of your business.",
  )


@safe
def invite_declined(business, user):
  notify(
    business.owner,
    f"{display_name(user)} declined your invite",
    "",
    push=False,
  )


@safe
def employee_removed(business, employee_user):
  notify(
    employee_user,
    f"You were removed from {business.business_name}",
    "You no longer have access to this business on Kosh.",
  )


@safe
def quotation_accepted(quotation):
  rfq = quotation.rfq
  notify(
    quotation.supplier_profile.user,
    f"Your quotation for {rfq.number} was accepted",
    f"{rfq.business.business_name} accepted your quotation of {rupees(quotation.grand_total)}.",
    kind=Kind.QUOTATION,
  )


@safe
def quotations_rejected(rfq, quotations):
  notify_many(
    [q.supplier_profile.user for q in quotations],
    f"Quotation not selected for {rfq.number}",
    f"{rfq.business.business_name} went with another supplier this time.",
    kind=Kind.QUOTATION,
    push=False,
  )

@safe
def rfq_deadline_reminder(rfq, hours):
  from procurement.models import RFQRecipient

  waiting = rfq.recipients.filter(
    status__in=[RFQRecipient.Status.SENT, RFQRecipient.Status.VIEWED]
  ).select_related("supplier_profile__user")
  users = [r.supplier_profile.user for r in waiting]
  if not users:
    return
  notify_many(
    users,
    f"{rfq.number} closes in about {hours} hours",
    f"{rfq.business.business_name} is waiting for your quotation. "
    f"Send it before {when(rfq.deadline)}.",
    kind=Notification.Kind.RFQ,
  )

@safe
def rfq_quotes_ready(rfq):
  from procurement.models import Quotation

  count = rfq.quotations.filter(status=Quotation.Status.SUBMITTED).count()
  if count:
    title = f"Quotations ready for {rfq.number}"
    body = f"{count} quotation(s) received. Compare them and choose a supplier."
  else:
    title = f"No quotations for {rfq.number}"
    body = "The deadline passed without any quotation."
  notify(rfq.business.owner, title, body, kind=Notification.Kind.QUOTATION)
