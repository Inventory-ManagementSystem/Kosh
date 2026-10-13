import math
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

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
from suppliers.models import SupplierProfile, SupplyCategory


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

    self.print_summary(business, products, outlets, supplier_count, opts["password"])


  def at(self, days_ago, hour, minute=0):
    day = timezone.localdate(self.now) - timedelta(days=days_ago)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))

  def backdate_movement(self, movement, when):
    StockMovement.objects.filter(pk=movement.pk).update(created_at=when)


  def reset(self):
    demo_users = User.objects.filter(email__iendswith=f"@{DEMO_DOMAIN}")
    business = Business.objects.filter(owner__email__iexact=OWNER_EMAIL).first()
    with transaction.atomic():
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