import math
import random
from datetime import datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Business, Employee
from inventory.ledger import create_dispatch, record_movement
from inventory.models import (
  Category, DispatchNote, Outlet, Product, StockMovement,
)
from inventory.reorder import calculate_reorder, get_dispatch_stats
from inventory.services import get_warehouse
from notifications.models import Notification
from procurement.models import (
  RFQ, Quotation, QuotationItem, RFQItem, RFQRecipient, ReorderSuggestion,
)
from procurement.services import calculate_line, calculate_totals, default_valid_until
from suppliers.models import Supplier, SupplierProfile, SupplyCategory


DEMO_DOMAIN = "kosh.test"
OWNER_EMAIL = f"demo-owner@{DEMO_DOMAIN}"
EMPLOYEE_EMAIL = f"demo-staff@{DEMO_DOMAIN}"
DEFAULT_PASSWORD = "Demo@1234"

BUSINESS = {
  "business_name": "Kosh Demo Retail",
  "business_type": "Retail Chain",
  "city": "Ghaziabad",
}

WAREHOUSE = {
  "name": "Central Warehouse",
  "address": "Plot 21, Industrial Area, Ghaziabad 201001",
}

OUTLETS = [
  ("Raj Nagar Store", "Raj Nagar, Ghaziabad 201002"),
  ("Indirapuram Store", "Indirapuram, Ghaziabad 201014"),
  ("Vaishali Store", "Vaishali, Ghaziabad 201010"),
  ("Noida Sector 18 Store", "Sector 18, Noida 201301"),
]

PRODUCTS = [
  ("Parle-G Biscuits 200g", "BIS-PARLEG-200", "Biscuits and Snacks", "20.00", "16.50", 40, 5, 30, True),
  ("Good Day Cashew 100g", "BIS-GOODDAY-100", "Biscuits and Snacks", "30.00", "24.00", 18, 5, 15, False),
  ("Lay's Classic Salted 52g", "SNK-LAYS-52", "Biscuits and Snacks", "20.00", "15.80", 25, 4, 20, False),
  ("Coca-Cola 750ml", "BEV-COKE-750", "Beverages", "40.00", "32.00", 22, 6, 20, True),
  ("Frooti Mango 600ml", "BEV-FROOTI-600", "Beverages", "35.00", "27.50", 15, 6, 15, False),
  ("Bisleri Water 1L", "BEV-BISLERI-1L", "Beverages", "20.00", "14.00", 45, 3, 40, False),
  ("Amul Taaza Milk 1L", "DAI-AMUL-1L", "Dairy", "68.00", "62.00", 30, 2, 20, True),
  ("Amul Butter 100g", "DAI-BUTTER-100", "Dairy", "58.00", "52.00", 10, 4, 8, False),
  ("Aashirvaad Atta 5kg", "GRO-ATTA-5KG", "Staples", "260.00", "228.00", 8, 7, 6, False),
  ("India Gate Basmati 1kg", "GRO-BASMATI-1KG", "Staples", "150.00", "128.00", 6, 7, 5, True),
  ("Fortune Sunflower Oil 1L", "GRO-OIL-1L", "Staples", "155.00", "138.00", 9, 7, 6, False),
  ("Tata Salt 1kg", "GRO-SALT-1KG", "Staples", "28.00", "22.00", 12, 5, 10, False),
  ("Surf Excel 1kg", "HOM-SURF-1KG", "Home Care", "140.00", "118.00", 7, 8, 5, False),
  ("Vim Dishwash Bar 200g", "HOM-VIM-200", "Home Care", "20.00", "15.50", 14, 8, 10, True),
  ("Colgate Strong Teeth 200g", "PER-COLGATE-200", "Personal Care", "110.00", "92.00", 9, 8, 6, False),
  ("Dove Soap 100g", "PER-DOVE-100", "Personal Care", "60.00", "49.00", 11, 8, 8, False),
]


SUPPLIERS = [
  ("Sharma FMCG Distributors", "sharma", "Ghaziabad", "201001",
   "09AABCS1001F1Z1", ["Groceries and FMCG", "Snacks and Confectionery"]),
  ("Gupta Beverages Agency", "gupta", "Ghaziabad", "201002",
   "09AABCG1002F1Z2", ["Beverages"]),
  ("Noida Dairy Supply Co", "noidadairy", "Noida", "201301",
   "09AABCN1003F1Z3", ["Dairy"]),
  ("Delhi Home and Personal Care", "dhpc", "Delhi", "110006",
   "07AABCD1004F1Z4", ["Household and Cleaning", "Personal Care"]),
  ("Capital Staples Traders", "capital", "Ghaziabad", "201010",
   "09AABCC1005F1Z5", ["Groceries and FMCG"]),
]
OWN_SUPPLIERS = ["sharma", "gupta", "noidadairy", "dhpc"]

NO_RESTOCK_LAST_DAYS = 36
RESTOCK_TO_DAYS = 30
OPENING_DAYS_OF_STOCK = 35


class Command(BaseCommand):
  help = "Create demo data: business, products, outlets, ~3 months of stock history and suppliers."

  def add_arguments(self, parser):
    parser.add_argument("--days", type=int, default=90, help="Days of dispatch history (default 90).")
    parser.add_argument("--reset", action="store_true", help="Delete the previous demo data first.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed, so every run gives the same data.")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for all demo accounts.")
    parser.add_argument("--force", action="store_true", help="Allow running when DEBUG is False.")
    parser.add_argument("--rfqs-only", action="store_true",help="Only (re)create the demo RFQs and quotations on the existing demo data.")

  def handle(self, *args, **opts):
    if not settings.DEBUG and not opts["force"]:
      raise CommandError(
        "DEBUG is False, so this looks like production. "
        "Add --force if you really want demo accounts here."
      )
    if opts["days"] < 30:
      raise CommandError("--days must be at least 30 so the reorder check has enough history.")

    self.rng = random.Random(opts["seed"])
    self.days = opts["days"]
    self.now = timezone.now()

    if opts["rfqs_only"]:
      business = Business.objects.filter(owner__email__iexact=OWNER_EMAIL).first()
      if business is None:
        raise CommandError("No demo data yet. Run seed_demo without --rfqs-only first.")
      with transaction.atomic():
        removed = self.delete_procurement(business)
        self.create_procurement(business)
      if removed:
        self.stdout.write(f"Removed {removed} old demo RFQs.")
      self.print_procurement_summary()
      return

    if opts["reset"]:
      self.reset()
    elif User.objects.filter(email__iexact=OWNER_EMAIL).exists():
      raise CommandError("Demo data already exists. Run again with --reset to recreate it.")

    with transaction.atomic():
      owner, business = self.create_business(opts["password"])
      categories = self.create_categories(business)
      products = self.create_products(business, categories)
      outlets = self.create_outlets(business)
      self.create_history(business, owner, products, outlets)
      supplier_count = self.create_suppliers(opts["password"])
      self.create_procurement(business)

    self.print_summary(business, products, outlets, supplier_count, opts["password"])
    self.print_procurement_summary()


  def at(self, days_ago, hour, minute=0):
    day = timezone.localdate(self.now) - timedelta(days=days_ago)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))

  def backdate_movement(self, movement, when):
    StockMovement.objects.filter(pk=movement.pk).update(created_at=when)


  def reset(self):
    demo_users = User.objects.filter(email__iendswith=f"@{DEMO_DOMAIN}")
    business = Business.objects.filter(owner__email__iexact=OWNER_EMAIL).first()
    with transaction.atomic():
      self.delete_procurement(business)
      if business:
        DispatchNote.objects.filter(business=business).delete()
        StockMovement.objects.filter(business=business).delete()
        Product.objects.filter(business=business).delete()
        Outlet.objects.filter(business=business).delete()
      count = demo_users.count()
      demo_users.delete()
    self.stdout.write(f"Removed old demo data ({count} demo accounts).")


  def create_user(self, email, name, password):
    user = User.objects.create_user(username=email, email=email, password=password)
    user.profile.name = name
    user.profile.save(update_fields=["name"])
    return user

  def create_business(self, password):
    owner = self.create_user(OWNER_EMAIL, "Demo Owner", password)
    business = Business.objects.create(owner=owner, **BUSINESS)

    warehouse = get_warehouse(business)
    warehouse.name = WAREHOUSE["name"]
    warehouse.address = WAREHOUSE["address"]
    warehouse.save(update_fields=["name", "address", "updated_at"])

    staff = self.create_user(EMPLOYEE_EMAIL, "Demo Staff", password)
    Employee.objects.create(user=staff, business=business, phone="9876500001")
    return owner, business

  def create_categories(self, business):
    names = sorted({p[2] for p in PRODUCTS})
    return {name: Category.objects.create(business=business, name=name) for name in names}

  def create_products(self, business, categories):
    warehouse = get_warehouse(business)
    products = []
    for (name, sku, cat, price, cost, daily, lead, safety, ends_low) in PRODUCTS:
      product = Product.objects.create(
        business=business,
        warehouse=warehouse,
        category=categories[cat],
        name=name,
        sku=sku,
        price=Decimal(price),
        cost_price=Decimal(cost),
        low_stock_threshold=daily * lead + safety,
        lead_time_days=lead,
        safety_stock=safety,
        reorder_quantity=daily * RESTOCK_TO_DAYS,
      )
      product.demo_daily = daily
      product.demo_ends_low = ends_low
      products.append(product)
    return products

  def create_outlets(self, business):
    return [
      Outlet.objects.create(business=business, name=name, address=address)
      for name, address in OUTLETS
    ]

  def create_history(self, business, owner, products, outlets):
    stock = {}
    opening_day = self.days + 1
    for product in products:
      qty = product.demo_daily * OPENING_DAYS_OF_STOCK
      movement = record_movement(
        business=business, product_id=product.id, change=qty,
        reason=StockMovement.Reason.OPENING_BALANCE, user=owner,
        note="Opening stock (demo)",
      )
      self.backdate_movement(movement, self.at(opening_day, 9))
      stock[product.id] = qty

    outlet_share = 1 / len(outlets)
    for days_ago in range(self.days, 0, -1):
      self.restock(business, owner, products, stock, days_ago)

      for index, outlet in enumerate(outlets):
        items = []
        for product in products:
          if self.rng.random() < 0.25:
            continue
          mean = product.demo_daily * outlet_share / 0.75
          qty = round(mean * self.rng.uniform(0.6, 1.4))
          qty = min(qty, stock[product.id])
          if qty > 0:
            items.append({"product_id": product.id, "quantity": qty})
            stock[product.id] -= qty
        if not items:
          continue

        when = self.at(days_ago, 11 + index, self.rng.randint(0, 59))
        note = create_dispatch(
          business=business, outlet_id=outlet.id, items=items, user=owner,
          dispatch_date=when.date(),
        )
        DispatchNote.objects.filter(pk=note.pk).update(created_at=when)
        StockMovement.objects.filter(dispatch_note=note).update(created_at=when)

  def restock(self, business, owner, products, stock, days_ago):
    for product in products:
      if product.demo_ends_low and days_ago <= NO_RESTOCK_LAST_DAYS:
        continue
      daily = product.demo_daily
      reorder_point = math.ceil(daily * product.lead_time_days) + product.safety_stock
      if stock[product.id] > reorder_point + 3 * daily:
        continue
      qty = daily * RESTOCK_TO_DAYS
      movement = record_movement(
        business=business, product_id=product.id, change=qty,
        reason=StockMovement.Reason.GRN_RECEIVED, user=owner,
        note="Restock (demo history)",
      )
      self.backdate_movement(movement, self.at(days_ago, 8, self.rng.randint(0, 59)))
      stock[product.id] += qty

  def create_suppliers(self, password):
    for index, (company, prefix, city, pincode, gstin, cat_names) in enumerate(SUPPLIERS, start=1):
      user = self.create_user(f"demo-supplier-{prefix}@{DEMO_DOMAIN}", company[:50], password)
      profile = SupplierProfile.objects.create(
        user=user,
        company_name=company,
        phone=f"98765{index:05d}",
        gstin=gstin,
        address=f"{city} {pincode}",
        city=city,
        pincode=pincode,
        is_verified=True,
        verified_at=self.now,
      )
      cats = []
      for name in cat_names:
        cat = SupplyCategory.objects.filter(name__iexact=name).first()
        if cat is None:
          cat = SupplyCategory.objects.create(name=name)
        cats.append(cat)
      profile.categories.set(cats)
    return len(SUPPLIERS)


  def print_summary(self, business, products, outlets, supplier_count, password):
    stats = get_dispatch_stats(business)
    low = []
    for product in Product.objects.filter(business=business):
      result = calculate_reorder(product, stats)
      if result.needs_reorder:
        low.append(f"{product.name} (stock {product.quantity}, reorder point {result.reorder_point})")

    dispatches = DispatchNote.objects.filter(business=business).count()
    movements = StockMovement.objects.filter(business=business).count()

    self.stdout.write(self.style.SUCCESS("Demo data created."))
    self.stdout.write(
      f"  {len(products)} products, {len(outlets)} outlets, {dispatches} dispatch notes, "
      f"{movements} stock movements, {supplier_count} verified suppliers"
    )
    self.stdout.write(f"  Owner:    {OWNER_EMAIL}")
    self.stdout.write(f"  Employee: {EMPLOYEE_EMAIL}")
    self.stdout.write(f"  Suppliers: demo-supplier-<name>@{DEMO_DOMAIN}")
    self.stdout.write(f"  Password for all demo accounts: {password}")
    self.stdout.write(f"  Products that need reordering now ({len(low)}):")
    for line in low:
      self.stdout.write(f"    - {line}")


  def delete_procurement(self, business):
    """Remove demo RFQs (cascades items, invitations, quotations) and their notifications."""
    demo_users = User.objects.filter(email__iendswith=f"@{DEMO_DOMAIN}")
    rfqs = RFQ.objects.filter(recipients__supplier_profile__user__in=demo_users)
    if business:
      rfqs = rfqs | RFQ.objects.filter(business=business)
    rfq_ids = list(rfqs.values_list("pk", flat=True).distinct())
    try: 
      from procurement.models import Payment
      Payment.objects.filter(quotation__rfq_id__in=rfq_ids).delete()
    except ImportError:
      pass
    count = RFQ.objects.filter(pk__in=rfq_ids).delete()[1].get("procurement.RFQ", 0)
    Notification.objects.filter(
      user__in=demo_users, kind__in=[Notification.Kind.RFQ, Notification.Kind.QUOTATION]
    ).delete()
    return count

  def create_procurement(self, business):
    self.p_business = business
    self.p_owner = business.owner
    self.p_stats = get_dispatch_stats(business)
    self.p_suppliers = {}
    for _, prefix, *_rest in SUPPLIERS:
      profile = SupplierProfile.objects.filter(user__email__iexact=self.supplier_email(prefix)).first()
      if profile is None:
        raise CommandError(f"Demo supplier {self.supplier_email(prefix)} not found.")
      self.p_suppliers[prefix] = profile
    self.p_own = self.link_own_suppliers()
    self.p_rfqs = []

    rfq, item = self.make_rfq("RFQ-0001", "GRO-BASMATI-1KG", RFQ.Status.OPEN,
                              created=self.now - timedelta(days=1),
                              deadline=self.now + timedelta(days=2), auto=True, alert=True,
                              notes="Deliver to Central Warehouse, back gate.")
    lead = item.product.lead_time_days
    sharma = self.invite(rfq, "sharma", RFQRecipient.Status.QUOTED, viewed_h=2, responded_h=5)
    self.quote(sharma, item, "126.00", "5", delivery_days=lead, advance_pct=25, after_h=5,
               notes="Price includes delivery to the Ghaziabad warehouse.")
    capital = self.invite(rfq, "capital", RFQRecipient.Status.QUOTED, viewed_h=4, responded_h=20)
    self.quote(capital, item, "121.50", "5", delivery_days=lead + 3, advance_pct=0, after_h=9)
    revised = Quotation.objects.get(recipient=capital)
    revised.revision = 2
    revised.submitted_at = rfq.created_at + timedelta(hours=20)
    revised.save(update_fields=["revision", "submitted_at"])
    self.demo_notify(self.p_owner, Notification.Kind.QUOTATION,
                     f"Quotation revised for {rfq.number}",
                     f"{capital.supplier_profile.company_name} quoted ₹{revised.grand_total} (incl. GST).",
                     revised.submitted_at)
    self.p_rfqs.append((rfq, "open, 2 quotations (Capital cheaper but late)"))

    rfq, _ = self.make_rfq("RFQ-0002", "BEV-COKE-750", RFQ.Status.OPEN,
                           created=self.now - timedelta(hours=3),
                           deadline=self.now + timedelta(days=1, hours=6), auto=True, alert=True)
    self.invite(rfq, "gupta")
    self.p_rfqs.append((rfq, "open, Gupta has not opened it"))

    rfq, _ = self.make_rfq("RFQ-0003", "DAI-AMUL-1L", RFQ.Status.OPEN,
                           created=self.now - timedelta(hours=8),
                           deadline=self.now + timedelta(days=1), auto=True, alert=True,
                           notes="Morning delivery before 8 AM please.")
    self.invite(rfq, "noidadairy", RFQRecipient.Status.VIEWED, viewed_h=1)
    self.p_rfqs.append((rfq, "open, Noida Dairy viewed, no quote yet"))


    rfq, item = self.make_rfq("RFQ-0004", "GRO-ATTA-5KG", RFQ.Status.AWARDED,
                              created=self.now - timedelta(days=6),
                              deadline=self.now - timedelta(days=3), auto=False, alert=True)
    lead = item.product.lead_time_days
    sharma = self.invite(rfq, "sharma", RFQRecipient.Status.QUOTED, viewed_h=1, responded_h=6)
    won = self.quote(sharma, item, "224.00", "5", delivery_days=lead, advance_pct=30, after_h=6,
                     status=Quotation.Status.ACCEPTED)
    capital = self.invite(rfq, "capital", RFQRecipient.Status.QUOTED, viewed_h=3, responded_h=26)
    self.quote(capital, item, "229.00", "5", delivery_days=max(lead - 1, 1), advance_pct=0,
               after_h=26, status=Quotation.Status.REJECTED)
    decided = rfq.deadline + timedelta(hours=4)
    self.demo_notify(sharma.supplier_profile.user, Notification.Kind.QUOTATION,
                     f"Your quotation for {rfq.number} was accepted",
                     f"{business.business_name} accepted your quotation of ₹{won.grand_total}.",
                     decided)
    self.demo_notify(capital.supplier_profile.user, Notification.Kind.QUOTATION,
                     f"Quotation not selected for {rfq.number}",
                     f"{business.business_name} went with another supplier this time.",
                     decided, read=True)
    self.p_rfqs.append((rfq, f"awarded to Sharma (advance ₹{won.advance_amount}), Capital rejected"))

    rfq, _ = self.make_rfq("RFQ-0005", "PER-DOVE-100", RFQ.Status.CLOSED,
                           created=self.now - timedelta(days=9),
                           deadline=self.now - timedelta(days=7), auto=False, alert=False,
                           quantity=240)
    dhpc = self.invite(rfq, "dhpc", RFQRecipient.Status.DECLINED, viewed_h=2, responded_h=3)
    self.demo_notify(self.p_owner, Notification.Kind.QUOTATION, f"Supplier declined {rfq.number}",
                     f"{dhpc.supplier_profile.company_name} won't be quoting on this RFQ.",
                     rfq.created_at + timedelta(hours=3), read=True)
    self.p_rfqs.append((rfq, "closed, Delhi Home & Personal Care declined"))

    rfq, _ = self.make_rfq("RFQ-0006", "BIS-PARLEG-200", RFQ.Status.CANCELLED,
                           created=self.now - timedelta(days=4),
                           deadline=self.now - timedelta(days=2), auto=False, alert=False,
                           quantity=1200, notes="Cancelled: bought locally instead.")
    self.invite(rfq, "sharma", RFQRecipient.Status.VIEWED, viewed_h=5)
    self.p_rfqs.append((rfq, "cancelled by the owner"))

    self.reorder_alert(Product.objects.get(business=business, sku="HOM-VIM-200"),
                       ReorderSuggestion.Status.OPEN)

  @staticmethod
  def supplier_email(prefix):
    return f"demo-supplier-{prefix}@{DEMO_DOMAIN}"

  def set_created(self, obj, when):
    type(obj).objects.filter(pk=obj.pk).update(created_at=when)
    obj.created_at = when

  def demo_notify(self, user, kind, title, body, when, read=False):
    notification = Notification.objects.create(
      user=user, kind=kind, title=title[:150], body=body,
      is_read=read, read_at=when if read else None,
    )
    self.set_created(notification, when)

  def link_own_suppliers(self):
    links = {}
    for prefix in OWN_SUPPLIERS:
      profile = self.p_suppliers[prefix]
      email = profile.user.email.lower()
      link = Supplier.objects.filter(business=self.p_business, email__iexact=email).first()
      if link is None:
        link = Supplier.objects.create(
          business=self.p_business, email=email, phone=profile.phone, linked_account=profile,
        )
      elif link.linked_account_id != profile.pk:
        link.linked_account = profile
        link.save(update_fields=["linked_account", "updated_at"])
      links[prefix] = link
    return links

  def reorder_alert(self, product, status):
    """Reuse the product's active low-stock alert (the nightly task may have made one)."""
    alert = ReorderSuggestion.objects.filter(
      product=product, status__in=ReorderSuggestion.ACTIVE
    ).first()
    if alert is None:
      result = calculate_reorder(product, self.p_stats)
      alert = ReorderSuggestion.objects.create(
        business=self.p_business,
        product=product,
        method=result.method,
        stock_at_creation=product.quantity,
        reorder_point=result.reorder_point,
        avg_daily_dispatch=result.avg_daily,
        suggested_quantity=result.suggested_quantity or product.reorder_quantity or 50,
      )
    alert.status = status
    alert.save(update_fields=["status", "updated_at"])
    return alert

  def make_rfq(self, number, sku, status, *, created, deadline, auto, alert, notes="",
               quantity=None):
    product = Product.objects.select_related("category").get(business=self.p_business, sku=sku)
    suggestion = (
      self.reorder_alert(product, ReorderSuggestion.Status.RFQ_CREATED) if alert else None
    )
    qty = quantity or (suggestion.suggested_quantity if suggestion else 0) \
      or product.reorder_quantity or 50
    rfq = RFQ.objects.create(
      business=self.p_business, number=number, reorder_suggestion=suggestion, status=status,
      include_platform_pool=True, deadline=deadline, notes=notes,
      created_by=None if auto else self.p_owner, 
    )
    self.set_created(rfq, created)
    item = RFQItem.objects.create(
      rfq=rfq, product=product, product_name=product.name, sku=product.sku, quantity=qty,
    )
    return rfq, item

  def invite(self, rfq, prefix, status=RFQRecipient.Status.SENT, viewed_h=None, responded_h=None):
    profile = self.p_suppliers[prefix]
    own = self.p_own.get(prefix)
    sent = rfq.created_at
    recipient = RFQRecipient.objects.create(
      rfq=rfq, supplier_profile=profile, supplier=own,
      source=RFQRecipient.Source.OWN if own else RFQRecipient.Source.PLATFORM,
      status=status,
      viewed_at=sent + timedelta(hours=viewed_h) if viewed_h is not None else None,
      responded_at=sent + timedelta(hours=responded_h) if responded_h is not None else None,
    )
    self.set_created(recipient, sent)
    self.demo_notify(
      profile.user, Notification.Kind.RFQ,
      f"New RFQ {rfq.number} from {self.p_business.business_name}",
      f"{rfq.items.first().product_name}. Quote by {timezone.localtime(rfq.deadline):%d %b, %I:%M %p}.",
      sent, read=viewed_h is not None,
    )
    return recipient

  def quote(self, recipient, item, unit_price, gst_rate, *, delivery_days, advance_pct, after_h,
            status=Quotation.Status.SUBMITTED, notes=""):
    rfq = recipient.rfq
    price, gst = Decimal(unit_price), Decimal(gst_rate)
    subtotal, tax, total = calculate_totals(
      [{"unit_price": price, "quantity": item.quantity, "gst_rate": gst}]
    )
    advance = (total * advance_pct / 100 / 100).quantize(Decimal("1"), ROUND_DOWN) * 100
    submitted = rfq.created_at + timedelta(hours=after_h)
    quotation = Quotation.objects.create(
      rfq=rfq, recipient=recipient, supplier_profile=recipient.supplier_profile, status=status,
      delivery_date=rfq.created_at.date() + timedelta(days=delivery_days),
      advance_amount=advance, valid_until=default_valid_until(rfq), notes=notes,
      subtotal=subtotal, tax_total=tax, grand_total=total, submitted_at=submitted,
    )
    self.set_created(quotation, submitted)
    line_subtotal, line_tax, line_total = calculate_line(price, item.quantity, gst)
    QuotationItem.objects.create(
      quotation=quotation, rfq_item=item, quantity=item.quantity, unit_price=price,
      gst_rate=gst, line_subtotal=line_subtotal, line_tax=line_tax, line_total=line_total,
    )
    self.demo_notify(
      self.p_owner, Notification.Kind.QUOTATION, f"New quotation for {rfq.number}",
      f"{recipient.supplier_profile.company_name} quoted ₹{total} (incl. GST).",
      submitted, read=rfq.status != RFQ.Status.OPEN,
    )
    return quotation

  def print_procurement_summary(self):
    self.stdout.write(self.style.SUCCESS("Demo RFQs and quotations created."))
    for rfq, label in self.p_rfqs:
      self.stdout.write(f"  {rfq.number}  {rfq.items.first().product_name:<26} {label}")
    self.stdout.write("  Vim Dishwash Bar: low-stock alert with no RFQ yet")
    self.stdout.write(f"  Try: {OWNER_EMAIL} (compare quotes on RFQ-0001), "
                      f"{self.supplier_email('gupta')} (quote on RFQ-0002)")