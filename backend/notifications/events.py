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

@safe
def purchase_order_issued(po):
  advance = (
    f" The advance of {rupees(po.advance_amount)} is already paid."
    if po.advance_amount > 0 else ""
  )
  notify(
    po.supplier_profile.user,
    f"New purchase order {po.number}",
    f"{po.business.business_name} ordered {items_label(po.rfq)} worth "
    f"{rupees(po.grand_total)}. Deliver by {po.delivery_date:%d %b %Y}.{advance}",
    kind=Kind.PURCHASE_ORDER,
  )
 
 
@safe
def rfq_awarded(rfq):
  from procurement.models import RFQRecipient
 
  waiting = rfq.recipients.filter(
    status__in=[RFQRecipient.Status.SENT, RFQRecipient.Status.VIEWED]
  ).select_related("supplier_profile__user")
  users = [r.supplier_profile.user for r in waiting]
  if not users:
    return
  notify_many(
    users,
    f"{rfq.number} was awarded",
    f"{rfq.business.business_name} chose another supplier for {items_label(rfq)}. "
    "No quotation is needed.",
    kind=Kind.RFQ,
    push=False,
  )

@safe
def advance_paid(po):
  notify(
    po.business.owner,
    f"Advance paid for {po.number}",
    f"We received your advance of {rupees(po.advance_amount)}. "
    f"{po.supplier_profile.company_name} has been sent the purchase order.",
    kind=Kind.PAYMENT,
  )


@safe
def advance_expired(po):
  notify(
    po.business.owner,
    f"{po.number} cancelled: advance not paid",
    f"The advance of {rupees(po.advance_amount)} wasn't paid by {when(po.advance_due_by)}, "
    f"so the order was cancelled. You can accept a quotation for {po.rfq.number} again.",
    kind=Kind.PAYMENT,
  )


@safe
def advance_refunded(po, amount):
  notify(
    po.business.owner,
    f"Refund started for {po.number}",
    f"Your payment of {rupees(amount)} came in after the order was closed, "
    f"so it's being refunded to the original payment method.",
    kind=Kind.PAYMENT,
  )

@safe
def goods_dispatched(po, shipment, invoice):
  sent = {s.purchase_order_item_id: s.quantity for s in shipment.items.all()}
  short = []
  for item in po.items.all():
    gap = item.quantity - sent.get(item.id, 0)
    if gap > 0:
      short.append(f"{item.product_name} ({gap} short)")

  body = (
    f"{po.supplier_profile.company_name} dispatched {po.number}. "
    f"Invoice {invoice.number} is {rupees(invoice.grand_total)}; "
    f"{rupees(invoice.balance_due)} is due after delivery. "
    f"Expected by {shipment.expected_delivery_date:%d %b %Y}."
  )
  if invoice.refund_due > 0:
    body += (
      f" The advance was {rupees(invoice.refund_due)} more than this invoice, "
      "so that amount is owed back."
    )
  if shipment.is_late:
    body += f" That is {shipment.late_by_days} day(s) later than the order date."
  if short:
    body += " Less than ordered: " + list_names(short) + "."

  title = f"{po.number} was dispatched" + (" (partial)" if short else "")
  notify(po.business.owner, title, body, kind=Kind.PURCHASE_ORDER)


def _what(payout):
  return "advance" if payout.kind == "advance" else "balance payment"


def _deduction_note(payout):
  if payout.deducted_amount and payout.deducted_amount > 0:
    return (f" {rupees(payout.deducted_amount)} was held back to repay an earlier "
            "overpayment.")
  return ""


@safe
def payout_on_hold(payout):
  notify(
    payout.supplier_profile.user,
    f"Add payout details to receive {rupees(payout.amount)}",
    f"The {_what(payout)} for {payout.purchase_order.number} is ready to be sent to you. "
    "Add your bank account or UPI ID in payout settings and we'll send it right away.",
    kind=Kind.PAYMENT,
  )


@safe
def payout_sent(payout):
  po = payout.purchase_order
  utr = f" Bank reference (UTR): {payout.utr}." if payout.utr else ""
  if payout.amount > 0:
    title = f"{rupees(payout.amount)} {_what(payout)} sent for {po.number}"
    body = f"The {_what(payout)} for {po.number} has been credited to your account.{utr}"
  else:
    title = f"{po.number} {_what(payout)} used to repay an overpayment"
    body = "Nothing was sent this time."
  notify(
    payout.supplier_profile.user, title, body + _deduction_note(payout), kind=Kind.PAYMENT,
  )
  notify(
    po.business.owner,
    f"{_what(payout).capitalize()} released to {payout.supplier_profile.company_name}",
    f"{rupees(payout.gross_amount)} for {po.number} was settled with the supplier.",
    kind=Kind.PAYMENT,
    push=False,
  )


@safe
def payout_failed(payout):
  notify(
    payout.supplier_profile.user,
    f"Couldn't send {rupees(payout.amount)} for {payout.purchase_order.number}",
    f"{payout.failure_reason} Check your payout details; saving them again retries the payment.",
    kind=Kind.PAYMENT,
  )
@safe
def goods_received(po, grn, invoice):
  labels = {"short_received": "missing", "rejected": "rejected", "excess": "extra"}
  issues = [
    f"{d.receipt_item.purchase_order_item.product_name} ({d.quantity} {labels[d.kind]})"
    for d in grn.discrepancies.select_related("receipt_item__purchase_order_item")
    if d.kind in labels
  ]

  body = f"{po.business.business_name} confirmed delivery of {po.number} ({grn.number})."
  if invoice.discrepancy_credit > 0:
    body += (
      f" {rupees(invoice.discrepancy_credit)} was credited on {invoice.number}; "
      f"balance due is now {rupees(invoice.balance_due)}."
    )
  else:
    body += f" Balance due on {invoice.number}: {rupees(invoice.balance_due)}."
  if invoice.refund_due > 0:
    body += f" {rupees(invoice.refund_due)} of the advance is owed back."
  if issues:
    body += " Issues: " + list_names(issues) + "."

  title = f"{po.number} was received" + (" (with issues)" if issues else "")
  notify(po.supplier_profile.user, title, body, kind=Kind.PURCHASE_ORDER)


@safe
def balance_paid(po, invoice):
  notify(
    po.business.owner,
    f"Balance paid for {invoice.number}",
    f"We received {rupees(invoice.balance_due)} for {po.number}. "
    f"It is being sent to {po.supplier_profile.company_name}.",
    kind=Kind.PAYMENT,
  )


@safe
def supplier_debt_created(debt):
  po = debt.purchase_order
  notify(
    debt.supplier_profile.user,
    f"{rupees(debt.amount)} to repay for {po.number}",
    f"The goods accepted for {po.number} were worth less than the advance you received. "
    f"{rupees(debt.amount)} will be held back from your next payouts.",
    kind=Kind.PAYMENT,
  )


@safe
def owner_refund_sent(refund):
  notify(
    refund.invoice.business.owner,
    f"Refund of {rupees(refund.amount)} for {refund.invoice.number}",
    f"Part of your advance is being refunded to your original payment method "
    f"because fewer goods were accepted.",
    kind=Kind.PAYMENT,
  )

