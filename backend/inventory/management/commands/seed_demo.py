import math
import random
import string
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import Business, Employee, EmployeeInvite
from inventory.ledger import create_dispatch, record_movement
from inventory.models import Category, DispatchNote, Outlet, Product, StockMovement
from inventory.reorder import calculate_reorder, get_dispatch_stats
from inventory.services import get_warehouse
from notifications.models import Notification
from procurement.alert_services import create_alerts_for_business
from procurement.dispatch_services import _line_amounts, next_invoice_number
from procurement.models import (
  RFQ,
  GoodsReceipt,
  GoodsReceiptDiscrepancy,
  GoodsReceiptItem,
  Invoice,
  InvoiceItem,
  OwnerRefund,
  Payment,
  Payout,
  ProcurementSettings,
  PurchaseOrder,
  PurchaseOrderItem,
  Quotation,
  QuotationItem,
  ReorderSuggestion,
  RFQItem,
  RFQRecipient,
  Shipment,
  ShipmentItem,
  SupplierDebt,
)
from procurement.services import calculate_line, calculate_totals, default_valid_until
from suppliers.models import Supplier, SupplierPayoutAccount, SupplierProfile, SupplyCategory


IST = ZoneInfo("Asia/Kolkata")
CENT = Decimal("0.01")
ZERO = Decimal("0")
Kind = Notification.Kind
Disc = GoodsReceiptDiscrepancy.Kind

DEMO_DOMAIN = "kosh.test"
OWNER_EMAIL = f"demo-owner@{DEMO_DOMAIN}"
STAFF_EMAIL = f"demo-staff@{DEMO_DOMAIN}"
STAFF2_EMAIL = f"demo-staff2@{DEMO_DOMAIN}"
INVITEE_EMAIL = f"demo-invitee@{DEMO_DOMAIN}"
DEFAULT_PASSWORD = "Demo@1234"
MIN_DAYS = 80

BUSINESS = {"business_name": "Kosh Demo Retail", "business_type": "Retail Chain", "city": "Ghaziabad"}
WAREHOUSE = {"name": "Central Warehouse", "address": "Plot 21, Industrial Area, Ghaziabad 201001"}

OUTLETS = [
  ("Raj Nagar Store", "Raj Nagar, Ghaziabad 201002", None),
  ("Indirapuram Store", "Indirapuram, Ghaziabad 201014", None),
  ("Vaishali Store", "Vaishali, Ghaziabad 201010", None),
  ("Noida Sector 18 Store", "Sector 18, Noida 201301", None),
  ("Kavi Nagar Store", "Kavi Nagar, Ghaziabad 201002", 50),
]

GROCERY = "Groceries and FMCG"
SNACKS = "Snacks and Confectionery"
BEVERAGES = "Beverages"
DAIRY = "Dairy"
HOUSEHOLD = "Household and Cleaning"
PERSONAL = "Personal Care"


def P(name, sku, category, supply, price, cost, gst, daily, lead, safety, plan="normal", desc=""):
  return dict(name=name, sku=sku, category=category, supply=supply, price=price, cost=cost,
              gst=gst, daily=daily, lead=lead, safety=safety, plan=plan, desc=desc)


PRODUCTS = [
  P("Parle-G Biscuits 200g", "BIS-PARLEG-200", "Biscuits and Snacks", SNACKS, "20.00", "16.50", 5, 40, 5, 30),
  P("Good Day Cashew 100g", "BIS-GOODDAY-100", "Biscuits and Snacks", SNACKS, "30.00", "24.00", 5, 18, 5, 15),
  P("Lay's Classic Salted 52g", "SNK-LAYS-52", "Biscuits and Snacks", SNACKS, "20.00", "15.80", 5, 25, 4, 20),
  P("Maggi Masala Noodles 70g", "SNK-MAGGI-70", "Biscuits and Snacks", SNACKS, "14.00", "11.50", 5, 20, 4, 15,
    plan="discontinued", desc="Discontinued. Old 70g pack replaced by the 4-pack."),
  P("Coca-Cola 750ml", "BEV-COKE-750", "Beverages", BEVERAGES, "40.00", "32.00", 40, 22, 6, 20),
  P("Frooti Mango 600ml", "BEV-FROOTI-600", "Beverages", BEVERAGES, "35.00", "27.50", 5, 15, 6, 15),
  P("Bisleri Water 1L", "BEV-BISLERI-1L", "Beverages", BEVERAGES, "20.00", "14.00", 5, 45, 3, 40),
  P("Amul Taaza Milk 1L", "DAI-AMUL-1L", "Dairy", DAIRY, "68.00", "62.00", 0, 30, 2, 20,
    desc="UHT toned milk. Keep in the cold room."),
  P("Amul Butter 100g", "DAI-BUTTER-100", "Dairy", DAIRY, "58.00", "52.00", 5, 10, 4, 8),
  P("Aashirvaad Atta 5kg", "GRO-ATTA-5KG", "Staples", GROCERY, "260.00", "228.00", 5, 8, 7, 6),
  P("India Gate Basmati 1kg", "GRO-BASMATI-1KG", "Staples", GROCERY, "150.00", "128.00", 5, 6, 7, 5),
  P("Fortune Sunflower Oil 1L", "GRO-OIL-1L", "Staples", GROCERY, "155.00", "138.00", 5, 9, 7, 6),
  P("Tata Salt 1kg", "GRO-SALT-1KG", "Staples", GROCERY, "28.00", "22.00", 0, 12, 5, 10),
  P("Kissan Tomato Ketchup 950g", "GRO-KETCHUP-950", "Sauces and Spreads", GROCERY, "145.00", None, 5, 5, 6, 4,
    desc="Cost price not entered yet."),
  P("Patanjali Honey 500g", "GRO-HONEY-500", "Sauces and Spreads", None, "199.00", "165.00", 5, 3, 10, 3,
    plan="slow", desc="Slow mover. No supply category set yet."),
  P("Surf Excel 1kg", "HOM-SURF-1KG", "Home Care", HOUSEHOLD, "140.00", "118.00", 18, 7, 8, 5),
  P("Vim Dishwash Bar 200g", "HOM-VIM-200", "Home Care", HOUSEHOLD, "20.00", "15.50", 18, 14, 8, 10),
  P("Colgate Strong Teeth 200g", "PER-COLGATE-200", "Personal Care", PERSONAL, "110.00", "92.00", 5, 9, 8, 6),
  P("Dove Soap 100g", "PER-DOVE-100", "Personal Care", PERSONAL, "60.00", "49.00", 5, 11, 8, 8),
]

SUPPLIERS = [
  dict(key="sharma", company="Sharma FMCG Distributors", city="Ghaziabad", pincode="201001",
       gstin="09AABCS1001F1Z1", cats=[GROCERY, SNACKS], verified=True, own="Main FMCG distributor",
       payout=("bank", "Sharma FMCG Distributors", "HDFC0001234", "HDFC Bank", "4821")),
  dict(key="gupta", company="Gupta Beverages Agency", city="Ghaziabad", pincode="201002",
       gstin="09AABCG1002F1Z2", cats=[BEVERAGES], verified=True, own="Cold drinks and water",
       payout=("vpa", "guptabev@okhdfcbank")),
  dict(key="noidadairy", company="Noida Dairy Supply Co", city="Noida", pincode="201301",
       gstin="09AABCN1003F1Z3", cats=[DAIRY], verified=True, own="Milk and butter, early morning",
       payout=("vpa", "noidadairy@oksbi")),
  dict(key="dhpc", company="Delhi Home and Personal Care", city="Delhi", pincode="110006",
       gstin="07AABCD1004F1Z4", cats=[HOUSEHOLD, PERSONAL], verified=True, own="HPC distributor",
       payout=("bank", "Delhi Home and Personal Care", "ICIC0000456", "ICICI Bank", "9034")),
  dict(key="capital", company="Capital Staples Traders", city="Ghaziabad", pincode="201010",
       gstin="09AABCC1005F1Z5", cats=[GROCERY], verified=True, own=None, payout=None),
  dict(key="hindon", company="Hindon Wholesale Mart", city="Ghaziabad", pincode="201003",
       gstin="09AABCH1006F1Z6", cats=[BEVERAGES, SNACKS, PERSONAL], verified=True, own=None,
       payout=("vpa", "hindonmart@okaxis")),
  dict(key="lakshmi", company="Lakshmi Traders", city="Ghaziabad", pincode="201005",
       gstin="09AABCL1007F1Z7", cats=[GROCERY], verified=False, own="New, waiting for verification",
       payout=None),
]
UNLINKED_SUPPLIER = (f"raghav-foods@{DEMO_DOMAIN}", "9876512345", "Raghav Foods (not on Kosh yet)")

STOCK_EVENTS = [
  (64, "BEV-COKE-750", StockMovement.Reason.DAMAGED, -4, "Bottles broken while unloading"),
  (40, "DAI-AMUL-1L", StockMovement.Reason.DAMAGED, -6, "Packets leaked in the cold room"),
  (33, "GRO-SALT-1KG", StockMovement.Reason.ADJUSTMENT, -3, "Stock count correction"),
  (18, "HOM-VIM-200", StockMovement.Reason.ADJUSTMENT, 4, "Found a misplaced carton during the stock count"),
  (8, "BEV-BISLERI-1L", StockMovement.Reason.DAMAGED, -5, "Bottles crushed under a pallet"),
  (4, "BIS-PARLEG-200", StockMovement.Reason.DAMAGED, -10, "Rain water got into one carton"),
]

DISCONTINUED_LAST_DISPATCH = 60
DISCONTINUED_CLEAR_DAY = 58
SLOW_LAST_DISPATCH = 46
RESTOCK_TO_DAYS = 30
OPENING_DAYS_OF_STOCK = 35
LOW_RUNWAY_DAYS = 40
TOPUP_DAYS_BEFORE = 1
SLOW_OPENING_STOCK = 250


def D(days_ago, hour=None, minute=0):
  return ("d", days_ago, hour, minute)


def H(hours_ago):
  return ("h", hours_ago)


def invite(supplier, viewed=None, quote=None, declined=None):
  return dict(supplier=supplier, viewed=viewed, quote=quote, declined=declined)


def quote(factor, advance, at, delivery, notes="", revised_at=None, withdrawn=None):
  return dict(factor=factor, advance=advance, at=at, delivery=delivery, notes=notes,
              revised_at=revised_at, withdrawn=withdrawn)


SCENARIOS = [
  dict(
    key="staples", supply=GROCERY, skus=["GRO-ATTA-5KG", "GRO-OIL-1L"], created=D(34, 2, 10),
    auto=True, pool=True, notes="Deliver to Central Warehouse, back gate.",
    invites=[
      invite("sharma", viewed=6, quote=quote(0.98, 30, 9, D(26), "Rates include delivery to the warehouse.")),
      invite("capital", viewed=8, quote=quote(1.01, 0, 31, D(24))),
    ],
    award=dict(winner="sharma", accepted=D(31, 10, 0), paid=D(31, 10, 20)),
    dispatch=dict(at=D(29, 15, 0), expected=D(26), tracking="Tempo UP14 KT 4410"),
    grn=dict(at=D(26, 9, 30), by="staff"),
    balance=D(25, 18, 0),
  ),
  dict(
    key="beverages", supply=BEVERAGES, skus=["BEV-COKE-750", "BEV-BISLERI-1L"], created=D(26, 12, 0),
    auto=False, pool=False,
    invites=[invite("gupta", viewed=1, quote=quote(0.97, 0, 4, D(21), "Chilled van delivery."))],
    award=dict(winner="gupta", accepted=D(24, 13, 0)),
    dispatch=dict(at=D(23, 11, 0), expected=D(21), tracking="Gupta van DL1L AB 2201"),
    grn=dict(at=D(21, 9, 15), by="staff", short={"BEV-BISLERI-1L": 12}, rejected={"BEV-COKE-750": 6},
             notes={"BEV-COKE-750": "6 bottles broken in one crate",
                    "BEV-BISLERI-1L": "One case of 12 missing from the load"}),
    balance=D(20, 17, 30),
  ),
  dict(
    key="personal", supply=PERSONAL, skus=["PER-COLGATE-200", "PER-DOVE-100"], created=D(20, 2, 10),
    auto=True, pool=True,
    invites=[
      invite("dhpc", viewed=5, quote=quote(0.97, 60, 9, D(12), "60% advance, fresh stock from the company depot.")),
      invite("hindon", viewed=10, quote=quote(1.03, 0, 30, D(13))),
    ],
    award=dict(winner="dhpc", accepted=D(17, 9, 0), paid=D(17, 9, 30)),
    dispatch=dict(at=D(15, 14, 0), expected=D(12), ratio={"PER-DOVE-100": 0.5},
                  tracking="Half the Dove is on back order."),
    grn=dict(at=D(12, 10, 0), by="staff2", rejected={"PER-COLGATE-200": 0.5},
             notes={"PER-COLGATE-200": "Crushed cartons, tubes leaking"},
             grn_notes="Colgate cartons were water damaged."),
    balance=None,
  ),
  dict(
    key="home", supply=HOUSEHOLD, skus=["HOM-SURF-1KG"], created=D(14, 11, 0), auto=False, pool=False,
    invites=[invite("dhpc", viewed=2, quote=quote(0.98, 30, 5, D(6)))],
    award=dict(winner="dhpc", accepted=D(11, 10, 0), paid=D(11, 10, 15)),
    dispatch=dict(at=D(9, 16, 0), expected=D(6)),
    grn=dict(at=D(6, 10, 40), by="owner"),
    balance=None,
  ),
  dict(
    key="salt", supply=GROCERY, skus=["GRO-SALT-1KG"], created=D(13, 2, 10), auto=True, pool=True,
    invites=[
      invite("sharma", viewed=7, declined=8),
      invite("capital", viewed=9, quote=quote(1.0, 0, 10, D(8), withdrawn=30)),
    ],
    resume_after=3,
  ),
  dict(
    key="ketchup", supply=GROCERY, skus=["GRO-KETCHUP-950"], created=D(9, 12, 0), auto=False, pool=False,
    invites=[invite("sharma", viewed=5)],
    cancelled=D(8, 10, 0), cancel_note="Cancelled: bought from the local market.",
    resume_after=1,
  ),
  dict(
    key="butter", supply=DAIRY, skus=["DAI-BUTTER-100"], created=D(6, 2, 10), auto=True, pool=True,
    invites=[invite("noidadairy", viewed=4, quote=quote(0.98, 50, 8, D(-2)))],
    award=dict(winner="noidadairy", accepted=D(3, 8, 0), failed_payment=D(3, 8, 5), expire=True),
  ),
  dict(
    key="milk", supply=DAIRY, skus=["DAI-AMUL-1L"], created=D(5, 2, 10), auto=True, pool=True,
    notes="Morning delivery before 8 AM please.",
    invites=[invite("noidadairy", viewed=4, quote=quote(0.99, 0, 6, D(0)))],
    award=dict(winner="noidadairy", accepted=D(2, 9, 0)),
    dispatch=dict(at=D(1, 7, 0), expected=D(0), tracking="Cold-chain van, before 8 AM"),
  ),
  dict(
    key="basmati", supply=GROCERY, skus=["GRO-BASMATI-1KG"], created=D(5, 2, 10), auto=True, pool=True,
    invites=[
      invite("sharma", viewed=6, quote=quote(1.0, 25, 9, D(-3))),
      invite("capital", viewed=7, quote=quote(0.96, 25, 10, D(-2), revised_at=30)),
    ],
    award=dict(winner="capital", accepted=D(2, 11, 0), paid=D(2, 11, 30)),
  ),
  dict(
    key="lays", supply=SNACKS, skus=["SNK-LAYS-52"], created=D(4, 15, 0), auto=False, pool=True,
    invites=[
      invite("sharma", viewed=1, quote=quote(1.02, 0, 5, D(-4))),
      invite("hindon", viewed=3, quote=quote(0.95, 40, 20, D(-3), "40% advance, balance on delivery.")),
    ],
    award=dict(winner="hindon", accepted=H(3)),
  ),
  dict(
    key="frooti", supply=BEVERAGES, skus=["BEV-FROOTI-600"], created=H(20), auto=True, pool=True,
    invites=[
      invite("gupta", viewed=1, quote=quote(0.99, 20, 4, D(-5))),
      invite("hindon", viewed=2, quote=quote(0.97, 0, 6, D(-6), revised_at=14)),
    ],
  ),
  dict(
    key="snacks", supply=SNACKS, skus=["BIS-PARLEG-200", "BIS-GOODDAY-100"], created=H(2), auto=True, pool=True,
    invites=[invite("sharma", viewed=1), invite("hindon")],
  ),
]

LOW_ONLY = [("HOM-VIM-200", 0)]


class Command(BaseCommand):
  help = "Create demo data: business, staff, products, outlets, ~3 months of stock " \
         "history, suppliers and the full procurement flow."

  def add_arguments(self, parser):
    parser.add_argument("--days", type=int, default=90, help=f"Days of history (default 90, min {MIN_DAYS}).")
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
    if opts["days"] < MIN_DAYS:
      raise CommandError(f"--days must be at least {MIN_DAYS} so every demo story fits in the history.")

    self.rng = random.Random(opts["seed"])
    self.days = opts["days"]
    self.now = timezone.now()
    self.today = self.now.astimezone(IST).date()

    if opts["reset"]:
      self.reset()
    elif User.objects.filter(email__iexact=OWNER_EMAIL).exists():
      raise CommandError("Demo data already exists. Run again with --reset to recreate it.")

    with transaction.atomic():
      self.create_people(opts["password"])
      self.create_catalogue()
      self.create_outlets()
      self.create_suppliers(opts["password"])
      self.plan()
      self.create_history()
      self.create_procurement()
      self.finish()

    self.print_summary(opts["password"])

  def at(self, days_ago, hour, minute=0):
    day = self.today - timedelta(days=days_ago)
    return datetime.combine(day, time(hour, minute), tzinfo=IST)

  def t(self, spec):
    if spec[0] == "h":
      return self.now - timedelta(hours=spec[1])
    _, days_ago, hour, minute = spec
    return self.at(days_ago, hour, minute)

  def date(self, spec):
    return self.today - timedelta(days=spec[1])

  def after(self, start, hours):
    return min(start + timedelta(hours=hours), self.now - timedelta(minutes=1))

  def days_ago(self, when):
    return (self.today - when.astimezone(IST).date()).days

  def stamp(self, obj, **fields):
    type(obj).objects.filter(pk=obj.pk).update(**fields)
    for name, value in fields.items():
      setattr(obj, name, value)

  def rz_id(self, prefix):
    return f"{prefix}_DEMO" + "".join(self.rng.choices(string.ascii_letters + string.digits, k=10))

  def notify(self, user, kind, title, body, when):
    read = when < self.now - timedelta(days=2)
    note = Notification.objects.create(
      user=user, kind=kind, title=title[:150], body=body,
      is_read=read, read_at=when + timedelta(hours=1) if read else None,
    )
    self.stamp(note, created_at=when)

  def reset(self):
    demo_users = list(User.objects.filter(email__iendswith=f"@{DEMO_DOMAIN}").values_list("pk", flat=True))
    business = Business.objects.filter(owner__email__iexact=OWNER_EMAIL).first()
    profiles = list(SupplierProfile.objects.filter(user_id__in=demo_users).values_list("pk", flat=True))

    with transaction.atomic():
      po_filter = Q(supplier_profile_id__in=profiles)
      if business:
        po_filter |= Q(business=business)
      pos = list(PurchaseOrder.objects.filter(po_filter).values_list("pk", flat=True))
      payouts = Payout.objects.filter(Q(purchase_order_id__in=pos) | Q(supplier_profile_id__in=profiles))
      debts = SupplierDebt.objects.filter(Q(purchase_order_id__in=pos) | Q(supplier_profile_id__in=profiles))
      OwnerRefund.objects.filter(
        Q(payment__purchase_order_id__in=pos) | Q(invoice__purchase_order_id__in=pos)
        | Q(debt__in=debts) | Q(recovered_by__in=payouts)
      ).delete()
      debts.delete()
      payouts.delete()
      Payment.objects.filter(purchase_order_id__in=pos).delete()
      GoodsReceipt.objects.filter(purchase_order_id__in=pos).delete()
      Shipment.objects.filter(purchase_order_id__in=pos).delete()
      Invoice.objects.filter(Q(purchase_order_id__in=pos) | Q(supplier_profile_id__in=profiles)).delete()

      PurchaseOrder.objects.filter(pk__in=pos).delete()
      RFQRecipient.objects.filter(supplier_profile_id__in=profiles).delete()

      if business:
        ReorderSuggestion.objects.filter(business=business).delete()
        RFQ.objects.filter(business=business).delete()
        DispatchNote.objects.filter(business=business).delete()
        StockMovement.objects.filter(business=business).delete()
        Product.objects.filter(business=business).delete()
        Outlet.objects.filter(business=business).delete()
      count = User.objects.filter(pk__in=demo_users).delete()[1].get("auth.User", 0)
    self.stdout.write(f"Removed old demo data ({count} demo accounts).")

  def create_user(self, email, name, password, joined_days_ago):
    user = User.objects.create_user(username=email, email=email, password=password)
    user.profile.name = name
    user.profile.save(update_fields=["name"])
    self.stamp(user, date_joined=self.at(joined_days_ago, 10))
    return user

  def create_people(self, password):
    start = self.days + 2
    self.owner = self.create_user(OWNER_EMAIL, "Rohit Agarwal", password, start)
    self.business = Business.objects.create(owner=self.owner, **BUSINESS)
    self.stamp(self.business, created_at=self.at(start, 10, 30))

    warehouse = get_warehouse(self.business)
    warehouse.name = WAREHOUSE["name"]
    warehouse.address = WAREHOUSE["address"]
    warehouse.save(update_fields=["name", "address", "updated_at"])
    self.warehouse = warehouse

    ProcurementSettings.objects.update_or_create(
      business=self.business,
      defaults={"auto_rfq_include_manual": True, "auto_rfq_include_platform_pool": True},
    )

    self.staff = self.add_employee(STAFF_EMAIL, "Amit Verma", "9876511001", self.days - 2, password)
    self.staff2 = self.add_employee(STAFF2_EMAIL, "Pooja Singh", "9876511002", 45, password)
    self.users = {"owner": self.owner, "staff": self.staff, "staff2": self.staff2}

    self.invitee = self.create_user(INVITEE_EMAIL, "Neha Sharma", password, 3)
    invite_at = self.now - timedelta(hours=30)
    invite = EmployeeInvite.objects.create(
      business=self.business, email=INVITEE_EMAIL, phone="9876511003", status="pending",
    )
    self.stamp(invite, created_at=invite_at)
    self.notify(self.invitee, Kind.GENERAL, f"{self.business.business_name} invited you to their team",
                "Open your invites to accept or decline.", invite_at)

  def add_employee(self, email, name, phone, joined, password):
    user = self.create_user(email, name, password, joined + 1)
    employee = Employee.objects.create(user=user, business=self.business, phone=phone)
    self.stamp(employee, created_at=self.at(joined, 11))
    self.notify(self.owner, Kind.GENERAL, f"{name} joined your team",
                "They can now use Kosh as an employee of your business.", self.at(joined, 11))
    return user

  def supply_category(self, name):
    cat = SupplyCategory.objects.filter(name__iexact=name).first()
    if cat is None:
      cat = SupplyCategory.objects.create(name=name)
    elif not cat.is_active:
      cat.is_active = True
      cat.save(update_fields=["is_active"])
    return cat

  def create_catalogue(self):
    start = self.at(self.days + 1, 9)
    names = sorted({p["category"] for p in PRODUCTS})
    categories = {}
    for name in names:
      categories[name] = Category.objects.create(business=self.business, name=name)
      self.stamp(categories[name], created_at=start, updated_at=start)

    supply_names = {p["supply"] for p in PRODUCTS if p["supply"]}
    for s in SUPPLIERS:
      supply_names.update(s["cats"])
    self.supply = {name: self.supply_category(name) for name in sorted(supply_names)}

    self.products = []
    self.by_sku = {}
    for spec in PRODUCTS:
      daily, lead, safety = spec["daily"], spec["lead"], spec["safety"]
      product = Product.objects.create(
        business=self.business,
        warehouse=self.warehouse,
        category=categories[spec["category"]],
        supply_category=self.supply[spec["supply"]] if spec["supply"] else None,
        name=spec["name"],
        sku=spec["sku"],
        description=spec["desc"],
        price=Decimal(spec["price"]),
        cost_price=Decimal(spec["cost"]) if spec["cost"] else None,
        low_stock_threshold=daily * lead + safety,
        lead_time_days=lead,
        safety_stock=safety,
        reorder_quantity=daily * RESTOCK_TO_DAYS,
      )
      self.stamp(product, created_at=start)
      product.demo = spec
      self.products.append(product)
      self.by_sku[spec["sku"]] = product

  def create_outlets(self):
    self.outlets = []
    for name, address, closed in OUTLETS:
      outlet = Outlet.objects.create(business=self.business, name=name, address=address)
      self.stamp(outlet, created_at=self.at(self.days + 1, 9, 30))
      outlet.demo_closed = closed
      self.outlets.append(outlet)

  def create_suppliers(self, password):
    self.suppliers = {}
    self.links = {}
    self.payout_accounts = {}
    joined = self.days + 1
    for index, spec in enumerate(SUPPLIERS, start=1):
      user = self.create_user(f"demo-supplier-{spec['key']}@{DEMO_DOMAIN}", spec["company"][:50], password, joined)
      verified_at = self.at(joined - 1, 16) if spec["verified"] else None
      profile = SupplierProfile.objects.create(
        user=user,
        company_name=spec["company"],
        phone=f"98765{index:05d}",
        gstin=spec["gstin"],
        address=f"{spec['city']} {spec['pincode']}",
        city=spec["city"],
        pincode=spec["pincode"],
        is_verified=spec["verified"],
        verified_at=verified_at,
      )
      self.stamp(profile, created_at=self.at(joined, 15))
      profile.categories.set([self.supply[name] for name in spec["cats"]])
      self.suppliers[spec["key"]] = profile
      if spec["verified"]:
        self.notify(user, Kind.GENERAL, "Your supplier account is verified",
                    "You can now receive requests for quotation from businesses on Kosh.", verified_at)

      if spec["payout"]:
        self.payout_accounts[spec["key"]] = self.add_payout_account(profile, spec["payout"])

      if spec["own"]:
        when = self.at(joined - 2, 11)
        link = Supplier.objects.create(
          business=self.business, email=user.email.lower(), phone=profile.phone,
          label=spec["own"], linked_account=profile,
        )
        self.stamp(link, created_at=when, updated_at=when)
        self.links[spec["key"]] = link
        self.notify(user, Kind.GENERAL, f"{self.business.business_name} added you as a supplier",
                    "You'll get their requests for quotation here.", when)

    email, phone, label = UNLINKED_SUPPLIER
    Supplier.objects.create(business=self.business, email=email, phone=phone, label=label)

  def add_payout_account(self, profile, payout):
    method = payout[0]
    if method == "bank":
      _, holder, ifsc, bank, last4 = payout
      details = dict(method=SupplierPayoutAccount.Method.BANK_ACCOUNT, account_holder_name=holder,
                     ifsc=ifsc, bank_name=bank, account_last4=last4)
    else:
      details = dict(method=SupplierPayoutAccount.Method.UPI, vpa=payout[1])
    return SupplierPayoutAccount.objects.create(
      supplier_profile=profile, razorpay_contact_id=self.rz_id("cont"),
      razorpay_fund_account_id=self.rz_id("fa"), **details,
    )

  def plan(self):
    self.scenarios = []
    for spec in SCENARIOS:
      s = dict(spec)
      s["created_at"] = self.t(s["created"])
      s["deadline_at"] = s["created_at"] + timedelta(days=3)
      s["T"] = self.days_ago(s["created_at"])
      s["qty"] = {}
      s["alert"] = {}
      if s.get("award"):
        s["accepted_at"] = self.t(s["award"]["accepted"])
      if s.get("grn"):
        s["grn_at"] = self.t(s["grn"]["at"])
      self.scenarios.append(s)
      for when in [s["created_at"], s.get("accepted_at"), s.get("grn_at")]:
        if when is not None and when > self.now:
          raise CommandError(f"Demo story {s['key']} has an event in the future.")

    self.scenarios.sort(key=lambda s: s["created_at"])
    for number, s in enumerate(self.scenarios, start=1):
      s["rfq_no"] = f"RFQ-{number:04d}"
    awarded = sorted((s for s in self.scenarios if s.get("award")), key=lambda s: s["accepted_at"])
    for number, s in enumerate(awarded, start=1):
      s["po_no"] = f"PO-{number:04d}"
    received = sorted((s for s in self.scenarios if s.get("grn")), key=lambda s: s["grn_at"])
    for number, s in enumerate(received, start=1):
      s["grn_no"] = f"GRN-{number:04d}"

    self.stock_plan = {}
    self.grn_by_day = defaultdict(list)
    for s in self.scenarios:
      if s.get("grn"):
        resume = self.days_ago(s["grn_at"])
        self.grn_by_day[resume].append(s)
      elif s.get("resume_after"):
        resume = max(s["T"] - s["resume_after"], 0)
      else:
        resume = 0
      for sku in s["skus"]:
        self.stock_plan[sku] = self.low_plan(s["T"], resume)
    for sku, low_day in LOW_ONLY:
      self.stock_plan[sku] = self.low_plan(low_day, 0)
    self.quantities_due = defaultdict(list)
    for s in self.scenarios:
      self.quantities_due[s["T"]].append(s)

  @staticmethod
  def low_plan(low_day, resume):
    return dict(low_day=low_day, restock_day=low_day + LOW_RUNWAY_DAYS,
                topup_day=low_day + TOPUP_DAYS_BEFORE, resume=resume)

  def create_history(self):
    self.stock = {}
    self.start_stock = {}
    self.dispatched = defaultdict(lambda: defaultdict(int))
    opening_day = self.days + 1
    for product in self.products:
      if product.demo["plan"] == "slow":
        qty = SLOW_OPENING_STOCK
      else:
        qty = product.demo["daily"] * OPENING_DAYS_OF_STOCK
      self.move(product, qty, StockMovement.Reason.OPENING_BALANCE, self.owner, "Opening stock",
                self.at(opening_day, 9))

    events = defaultdict(list)
    for days_ago, sku, reason, change, note in STOCK_EVENTS:
      events[days_ago].append((self.by_sku[sku], reason, change, note))

    for days_ago in range(self.days, 0, -1):
      self.start_stock[days_ago] = dict(self.stock)
      self.resolve_quantities(days_ago)
      self.restock(days_ago)
      for s in self.grn_by_day.get(days_ago, []):
        self.receive_stock(s)
      self.dispatch_day(days_ago)
      for product, reason, change, note in events.get(days_ago, []):
        if self.stock[product.id] + change >= 0:
          self.move(product, change, reason, self.staff, note, self.at(days_ago, 19, 0))
      if days_ago == DISCONTINUED_CLEAR_DAY:
        for product in self.products:
          if product.demo["plan"] == "discontinued" and self.stock[product.id] > 0:
            self.move(product, -self.stock[product.id], StockMovement.Reason.ADJUSTMENT, self.owner,
                      "Discontinued: remaining stock returned to the distributor",
                      self.at(days_ago, 18, 0))

    self.start_stock[0] = dict(self.stock)
    self.resolve_quantities(0)

  def move(self, product, change, reason, user, note, when):
    movement = record_movement(
      business=self.business, product_id=product.id, change=change, reason=reason, user=user, note=note,
    )
    self.stamp(movement, created_at=when)
    self.stock[product.id] = self.stock.get(product.id, 0) + change
    return movement

  def restock(self, days_ago):
    for product in self.products:
      spec = product.demo
      if spec["plan"] == "slow":
        continue
      if spec["plan"] == "discontinued" and days_ago <= DISCONTINUED_LAST_DISPATCH + 2:
        continue
      daily = spec["daily"]
      reorder_point = math.ceil(daily * spec["lead"]) + spec["safety"]
      when = self.at(days_ago, 8, self.rng.randint(0, 59))

      plan = self.stock_plan.get(spec["sku"])
      if plan and plan["topup_day"] <= days_ago <= plan["restock_day"]:
        target = self.glide_target(product, plan, days_ago)
        due = days_ago in (plan["restock_day"], plan["topup_day"]) \
          or self.stock[product.id] < target - 4 * daily
        if due and target > self.stock[product.id]:
          self.move(product, target - self.stock[product.id], StockMovement.Reason.GRN_RECEIVED,
                    self.owner, "Purchase received outside Kosh", when)
        continue
      if plan and plan["resume"] <= days_ago < plan["restock_day"]:
        continue

      if self.stock[product.id] > reorder_point + 3 * daily:
        continue
      self.move(product, daily * RESTOCK_TO_DAYS, StockMovement.Reason.GRN_RECEIVED, self.owner,
                "Purchase received outside Kosh", when)

  def glide_target(self, product, plan, days_ago):
    spec = product.demo
    avg = sum(self.dispatched[d][product.id] for d in range(days_ago + 1, days_ago + 31)) / 30
    avg = avg or spec["daily"]
    reorder_point = min(math.ceil(spec["daily"] * spec["lead"]), math.ceil(avg * spec["lead"])) + spec["safety"]
    low = reorder_point - math.ceil(min(2 * max(spec["daily"], avg), 0.4 * reorder_point))
    to_topup = plan["topup_day"] - plan["low_day"]
    beyond = max(days_ago - plan["topup_day"], 0)
    return max(low + math.ceil(to_topup * avg) + math.floor(0.7 * beyond * avg), 0)

  def dispatcher(self, days_ago):
    staff_from = self.days - 2
    choices = [self.owner]
    if days_ago <= staff_from:
      choices += [self.staff] * 5
    if days_ago <= 45:
      choices += [self.staff2] * 3
    return self.rng.choice(choices)

  def dispatch_day(self, days_ago):
    open_outlets = [o for o in self.outlets if o.demo_closed is None or days_ago > o.demo_closed]
    share = 1 / len(open_outlets)
    for index, outlet in enumerate(open_outlets):
      items = []
      for product in self.products:
        plan = product.demo["plan"]
        if plan == "discontinued" and days_ago <= DISCONTINUED_LAST_DISPATCH:
          continue
        if plan == "slow" and days_ago < SLOW_LAST_DISPATCH:
          continue
        if self.rng.random() < 0.25:
          continue
        mean = product.demo["daily"] * share / 0.75
        qty = min(round(mean * self.rng.uniform(0.6, 1.4)), self.stock[product.id])
        if qty > 0:
          items.append({"product_id": product.id, "quantity": qty})
      if not items:
        continue

      when = self.at(days_ago, 11 + index, self.rng.randint(0, 59))
      note = create_dispatch(
        business=self.business, outlet_id=outlet.id, items=items, user=self.dispatcher(days_ago),
        dispatch_date=when.date(),
      )
      DispatchNote.objects.filter(pk=note.pk).update(created_at=when)
      StockMovement.objects.filter(dispatch_note=note).update(created_at=when)
      for item in items:
        self.stock[item["product_id"]] -= item["quantity"]
        self.dispatched[days_ago][item["product_id"]] += item["quantity"]

  def resolve_quantities(self, days_ago):
    for s in self.quantities_due.get(days_ago, []):
      for sku in s["skus"]:
        product = self.by_sku[sku]
        stock = self.start_stock[days_ago][product.id]
        window = range(days_ago + 1, days_ago + 31)
        avg = sum(self.dispatched[d][product.id] for d in window) / 30
        reorder_point = math.ceil(avg * product.lead_time_days) + product.safety_stock
        target = avg * (product.lead_time_days + 30) + product.safety_stock
        suggested = max(math.ceil(target - stock), 0) or product.reorder_quantity
        s["alert"][sku] = dict(stock=stock, avg=round(avg, 2), reorder_point=reorder_point,
                               suggested=suggested)
        qty = suggested if s["auto"] else int(math.ceil(suggested / 10) * 10)
        s["qty"][sku] = max(qty, 1)

  def lines_for(self, s):
    if "lines" in s:
      return s["lines"]
    dispatch = s.get("dispatch") or {}
    grn = s.get("grn") or {}
    lines = {}
    for sku in s["skus"]:
      ordered = s["qty"][sku]
      ratio = dispatch.get("ratio", {}).get(sku)
      dispatched = ordered if ratio is None else max(1, int(ordered * ratio))
      received = max(dispatched - grn.get("short", {}).get(sku, 0), 0)
      rejected = grn.get("rejected", {}).get(sku, 0)
      if isinstance(rejected, float):
        rejected = int(round(received * rejected))
      rejected = min(rejected, received)
      lines[sku] = dict(ordered=ordered, dispatched=dispatched, received=received,
                        rejected=rejected, accepted=received - rejected)
    s["lines"] = lines
    return lines

  def receive_stock(self, s):
    user = self.users[s["grn"]["by"]]
    for sku, line in self.lines_for(s).items():
      if line["accepted"] > 0:
        self.move(self.by_sku[sku], line["accepted"], StockMovement.Reason.GRN_RECEIVED, user,
                  f"{s['grn_no']} / {s['po_no']}", s["grn_at"])

  def create_procurement(self):
    for s in self.scenarios:
      self.build_rfq(s)
    steps = []
    for s in self.scenarios:
      if s.get("award"):
        steps.append((s["accepted_at"], 0, self.build_order, s))
      if s.get("dispatch"):
        steps.append((self.t(s["dispatch"]["at"]), 1, self.build_dispatch, s))
      if s.get("grn"):
        steps.append((s["grn_at"], 2, self.build_receipt, s))
      if s.get("balance"):
        steps.append((self.t(s["balance"]), 3, self.pay_balance, s))
    for _, _, step, s in sorted(steps, key=lambda row: (row[0], row[1])):
      step(s)
    for s in self.scenarios:
      self.close_rfq(s)

  def build_rfq(self, s):
    created = s["created_at"]
    rfq = RFQ.objects.create(
      business=self.business, number=s["rfq_no"], status=RFQ.Status.OPEN,
      include_platform_pool=s["pool"], supply_category=self.supply[s["supply"]],
      deadline=s["deadline_at"], notes=s.get("notes", ""),
      created_by=None if s["auto"] else self.owner,
    )
    self.stamp(rfq, created_at=created, updated_at=created)
    s["rfq"] = rfq
    s["items"] = {}
    for sku in s["skus"]:
      product = self.by_sku[sku]
      s["items"][sku] = RFQItem.objects.create(
        rfq=rfq, product=product, product_name=product.name, sku=product.sku, quantity=s["qty"][sku],
      )

    alert_at = created - (timedelta(minutes=10) if s["auto"] else timedelta(hours=5))
    s["alerts"] = []
    low = []
    for sku in s["skus"]:
      product = self.by_sku[sku]
      a = s["alert"][sku]
      alert = ReorderSuggestion.objects.create(
        business=self.business, product=product, rfq=rfq, status=ReorderSuggestion.Status.RFQ_CREATED,
        method="formula", stock_at_creation=a["stock"], reorder_point=a["reorder_point"],
        avg_daily_dispatch=a["avg"], suggested_quantity=max(a["suggested"], 1),
      )
      self.stamp(alert, created_at=alert_at, updated_at=created)
      s["alerts"].append(alert)
      low.append((product, a["stock"]))
    if len(low) == 1:
      title, body = f"{low[0][0].name} is low on stock", f"Only {low[0][1]} left. Create an RFQ to restock."
    else:
      title = f"{len(low)} products are low on stock"
      body = f"{', '.join(p.name for p, _ in low)}. Create RFQs to restock."
    self.notify(self.owner, Kind.LOW_STOCK, title, body, alert_at)

    if len(s["skus"]) == 1:
      need = f"{self.business.business_name} needs {s['qty'][s['skus'][0]]} x {self.by_sku[s['skus'][0]].name}."
    else:
      need = f"{self.business.business_name} needs {len(s['skus'])} products ({s['supply']})."
    deadline_text = f"{s['deadline_at'].astimezone(IST):%d %b %Y}"

    s["recipients"] = {}
    s["quotes"] = {}
    for inv in s["invites"]:
      key = inv["supplier"]
      profile = self.suppliers[key]
      link = self.links.get(key)
      recipient = RFQRecipient.objects.create(
        rfq=rfq, supplier_profile=profile, supplier=link,
        source=RFQRecipient.Source.OWN if link else RFQRecipient.Source.PLATFORM,
      )
      self.stamp(recipient, created_at=created)
      s["recipients"][key] = recipient
      self.notify(profile.user, Kind.RFQ, f"New RFQ {rfq.number}",
                  f"{need} Send your quotation before {deadline_text}.", created)

      fields = {}
      if inv["viewed"] is not None:
        fields.update(status=RFQRecipient.Status.VIEWED, viewed_at=self.after(created, inv["viewed"]))
      if inv["declined"] is not None:
        declined_at = self.after(created, inv["declined"])
        fields.update(status=RFQRecipient.Status.DECLINED, responded_at=declined_at)
        self.notify(self.owner, Kind.QUOTATION, f"Supplier declined {rfq.number}",
                    f"{profile.company_name} won't be quoting on this RFQ.", declined_at)
      if fields:
        self.stamp(recipient, **fields)
      if inv["quote"]:
        s["quotes"][key] = self.make_quote(s, recipient, inv["quote"])

    if s["auto"]:
      count = len(s["invites"])
      self.notify(self.owner, Kind.RFQ, f"RFQ {rfq.number} created automatically",
                  f"{len(s['skus'])} {s['supply']} product(s) are running low. "
                  f"The RFQ was sent to {count} supplier(s).", created)

  def unit_price(self, product, factor):
    base = product.cost_price if product.cost_price is not None else product.price * Decimal("0.8")
    gst = Decimal(product.demo["gst"])
    net = base / (1 + gst / 100) * Decimal(str(factor))
    return max((net * 2).quantize(Decimal("1")) / 2, Decimal("0.50")).quantize(CENT)

  def make_quote(self, s, recipient, q):
    rfq = s["rfq"]
    first_at = self.after(rfq.created_at, q["at"])
    final_at = self.after(rfq.created_at, q["revised_at"] or q["at"])
    rows = []
    for sku, item in s["items"].items():
      product = self.by_sku[sku]
      rows.append(dict(rfq_item=item, quantity=item.quantity,
                       unit_price=self.unit_price(product, q["factor"]),
                       gst_rate=Decimal(product.demo["gst"])))
    subtotal, tax, total = calculate_totals(rows)
    advance = (total * q["advance"] / 100 / 100).quantize(Decimal("1"), ROUND_DOWN) * 100

    quotation = Quotation.objects.create(
      rfq=rfq, recipient=recipient, supplier_profile=recipient.supplier_profile,
      status=Quotation.Status.SUBMITTED, delivery_date=self.date(q["delivery"]),
      advance_amount=advance, valid_until=default_valid_until(rfq), notes=q["notes"],
      subtotal=subtotal, tax_total=tax, grand_total=total,
      revision=2 if q["revised_at"] else 1, submitted_at=final_at,
    )
    self.stamp(quotation, created_at=first_at, updated_at=final_at)
    for row in rows:
      line_subtotal, line_tax, line_total = calculate_line(row["unit_price"], row["quantity"], row["gst_rate"])
      QuotationItem.objects.create(
        quotation=quotation, line_subtotal=line_subtotal, line_tax=line_tax, line_total=line_total, **row,
      )

    company = recipient.supplier_profile.company_name
    self.stamp(recipient, status=RFQRecipient.Status.QUOTED,
               viewed_at=recipient.viewed_at or first_at, responded_at=final_at)
    self.notify(self.owner, Kind.QUOTATION, f"New quotation for {rfq.number}",
                f"{company} quoted ₹{total} (incl. GST).", first_at)
    if q["revised_at"]:
      self.notify(self.owner, Kind.QUOTATION, f"Quotation revised for {rfq.number}",
                  f"{company} quoted ₹{total} (incl. GST).", final_at)
    if q["withdrawn"]:
      gone = self.after(rfq.created_at, q["withdrawn"])
      self.stamp(quotation, status=Quotation.Status.WITHDRAWN, updated_at=gone)
      self.stamp(recipient, status=RFQRecipient.Status.VIEWED, responded_at=None)
      self.notify(self.owner, Kind.QUOTATION, f"Quotation withdrawn for {rfq.number}",
                  f"{company} withdrew their quotation.", gone)
    return quotation

  def build_order(self, s):
    award = s["award"]
    rfq = s["rfq"]
    quotation = s["quotes"][award["winner"]]
    supplier = quotation.supplier_profile
    accepted = s["accepted_at"]
    advance = quotation.advance_amount
    due_by = None
    if advance > 0:
      due_by = accepted + timedelta(hours=settings.PO_ADVANCE_EXPIRY_HOURS)
      if award.get("expire") and due_by > self.now - timedelta(hours=1):
        due_by = self.now - timedelta(hours=1)

    po = PurchaseOrder.objects.create(
      business=self.business, number=s["po_no"], rfq=rfq, quotation=quotation,
      supplier_profile=supplier, status=PurchaseOrder.Status.AWAITING_ADVANCE,
      subtotal=quotation.subtotal, tax_total=quotation.tax_total, grand_total=quotation.grand_total,
      advance_amount=advance, delivery_date=quotation.delivery_date, advance_due_by=due_by,
    )
    self.stamp(po, created_at=accepted, updated_at=accepted)
    s["po"] = po
    s["po_items"] = {}
    for line in quotation.items.select_related("rfq_item"):
      s["po_items"][line.rfq_item.sku] = PurchaseOrderItem.objects.create(
        purchase_order=po, product_id=line.rfq_item.product_id, product_name=line.rfq_item.product_name,
        sku=line.rfq_item.sku, quantity=line.quantity, unit_price=line.unit_price, gst_rate=line.gst_rate,
        line_subtotal=line.line_subtotal, line_tax=line.line_tax, line_total=line.line_total,
      )
    self.stamp(quotation, status=Quotation.Status.ACCEPTED, updated_at=accepted)
    self.stamp(rfq, status=RFQ.Status.AWARDED, updated_at=accepted)

    if advance <= 0:
      self.issue_order(s, accepted)
      return

    self.notify(supplier.user, Kind.QUOTATION, f"Your quotation for {rfq.number} was accepted",
                f"{self.business.business_name} accepted your quotation of ₹{quotation.grand_total}.", accepted)
    if award.get("failed_payment"):
      tried = self.t(award["failed_payment"])
      payment = Payment.objects.create(
        purchase_order=po, kind=Payment.Kind.ADVANCE, amount=advance, status=Payment.Status.FAILED,
        razorpay_order_id=self.rz_id("order"), failure_reason="Payment was declined by the bank.",
      )
      self.stamp(payment, created_at=tried, updated_at=tried + timedelta(minutes=2))
    if award.get("paid"):
      paid = self.t(award["paid"])
      payment = Payment.objects.create(
        purchase_order=po, kind=Payment.Kind.ADVANCE, amount=advance, status=Payment.Status.PAID,
        razorpay_order_id=self.rz_id("order"), razorpay_payment_id=self.rz_id("pay"), paid_at=paid,
      )
      self.stamp(payment, created_at=paid - timedelta(minutes=3), updated_at=paid)
      s["advance_payment"] = payment
      self.notify(self.owner, Kind.PAYMENT, f"Advance paid for {po.number}",
                  f"We received your advance of ₹{advance}. "
                  f"{supplier.company_name} has been sent the purchase order.", paid)
      self.issue_order(s, paid)
    elif award.get("expire"):
      cancelled = po.advance_due_by + timedelta(minutes=10)
      cancelled = min(cancelled, self.now - timedelta(minutes=30))
      self.stamp(po, status=PurchaseOrder.Status.CANCELLED, cancelled_at=cancelled, updated_at=cancelled)
      self.stamp(quotation, status=Quotation.Status.SUBMITTED, updated_at=cancelled)
      new_status = RFQ.Status.OPEN if rfq.deadline > cancelled else RFQ.Status.CLOSED
      self.stamp(rfq, status=new_status, updated_at=cancelled)
      s["po_cancelled"] = True
      self.notify(self.owner, Kind.PAYMENT, f"{po.number} cancelled: advance not paid",
                  f"The advance of ₹{advance} wasn't paid by "
                  f"{po.advance_due_by.astimezone(IST):%d %b, %I:%M %p}, so the order was cancelled. "
                  f"You can accept a quotation for {rfq.number} again.", cancelled)

  def issue_order(self, s, when):
    po, rfq = s["po"], s["rfq"]
    self.stamp(po, status=PurchaseOrder.Status.ISSUED, issued_at=when, updated_at=when)
    items = self.items_label(s)
    advance = f" The advance of ₹{po.advance_amount} is already paid." if po.advance_amount > 0 else ""
    self.notify(po.supplier_profile.user, Kind.PURCHASE_ORDER, f"New purchase order {po.number}",
                f"{self.business.business_name} ordered {items} worth ₹{po.grand_total}. "
                f"Deliver by {po.delivery_date:%d %b %Y}.{advance}", when)

    losers = [q for key, q in s["quotes"].items()
              if q.pk != po.quotation_id and q.status == Quotation.Status.SUBMITTED]
    for q in losers:
      self.stamp(q, status=Quotation.Status.REJECTED, updated_at=when)
      self.notify(q.supplier_profile.user, Kind.QUOTATION, f"Quotation not selected for {rfq.number}",
                  f"{self.business.business_name} went with another supplier this time.", when)
    for recipient in s["recipients"].values():
      if recipient.status in (RFQRecipient.Status.SENT, RFQRecipient.Status.VIEWED):
        self.notify(recipient.supplier_profile.user, Kind.RFQ, f"{rfq.number} was awarded",
                    f"{self.business.business_name} chose another supplier for {items}. "
                    "No quotation is needed.", when)

  def items_label(self, s):
    if len(s["skus"]) == 1:
      return self.by_sku[s["skus"][0]].name
    return f"{len(s['skus'])} products ({s['supply']})"

  def build_dispatch(self, s):
    po = s["po"]
    supplier = po.supplier_profile
    dispatch = s["dispatch"]
    sent_at = self.t(dispatch["at"])
    expected = self.date(dispatch["expected"])
    lines = self.lines_for(s)

    shipment = Shipment.objects.create(
      purchase_order=po, dispatched_at=sent_at, expected_delivery_date=expected,
      tracking_note=dispatch.get("tracking", ""), created_by=supplier.user,
    )
    self.stamp(shipment, created_at=sent_at)
    invoice_lines = []
    for sku, item in s["po_items"].items():
      qty = lines[sku]["dispatched"]
      ShipmentItem.objects.create(shipment=shipment, purchase_order_item=item, quantity=qty)
      invoice_lines.append((item, qty, *_line_amounts(item, qty)))

    subtotal = sum((row[2] for row in invoice_lines), ZERO)
    tax_total = sum((row[3] for row in invoice_lines), ZERO)
    grand_total = subtotal + tax_total
    applied = min(po.advance_amount, grand_total)
    invoice = Invoice.objects.create(
      supplier_profile=supplier, business=self.business, purchase_order=po,
      number=next_invoice_number(supplier), issue_date=sent_at.astimezone(IST).date(),
      subtotal=subtotal, tax_total=tax_total, grand_total=grand_total,
      advance_applied=applied, balance_due=grand_total - applied, refund_due=po.advance_amount - applied,
    )
    self.stamp(invoice, created_at=sent_at, updated_at=sent_at)
    for item, qty, line_subtotal, line_tax, line_total in invoice_lines:
      InvoiceItem.objects.create(
        invoice=invoice, product_id=item.product_id, product_name=item.product_name, sku=item.sku,
        quantity=qty, unit_price=item.unit_price, gst_rate=item.gst_rate,
        line_subtotal=line_subtotal, line_tax=line_tax, line_total=line_total,
      )
    s["invoice"] = invoice
    s["shipment"] = shipment
    self.stamp(po, status=PurchaseOrder.Status.DISPATCHED, updated_at=sent_at)

    short = [f"{item.product_name} ({item.quantity - lines[sku]['dispatched']} short)"
             for sku, item in s["po_items"].items() if lines[sku]["dispatched"] < item.quantity]
    body = (f"{supplier.company_name} dispatched {po.number}. Invoice {invoice.number} is "
            f"₹{invoice.grand_total}; ₹{invoice.balance_due} is due after delivery. "
            f"Expected by {expected:%d %b %Y}.")
    if invoice.refund_due > 0:
      body += f" The advance was ₹{invoice.refund_due} more than this invoice, so that amount is owed back."
    if shipment.late_by_days:
      body += f" That is {shipment.late_by_days} day(s) later than the order date."
    if short:
      body += " Less than ordered: " + ", ".join(short) + "."
    self.notify(self.owner, Kind.PURCHASE_ORDER, f"{po.number} was dispatched" + (" (partial)" if short else ""),
                body, sent_at)

    if applied > 0 and s.get("advance_payment"):
      self.make_payout(s, Payout.Kind.ADVANCE, applied, sent_at + timedelta(minutes=5))

  def build_receipt(self, s):
    po, invoice = s["po"], s["invoice"]
    grn_spec = s["grn"]
    received_at = s["grn_at"]
    user = self.users[grn_spec["by"]]
    lines = self.lines_for(s)
    invoice_items = {i.product_id: i for i in invoice.items.all()}

    grn = GoodsReceipt.objects.create(
      business=self.business, purchase_order=po, number=s["grn_no"],
      notes=grn_spec.get("grn_notes", ""), received_by=user,
    )
    self.stamp(grn, created_at=received_at)
    credit_total = ZERO
    issues = []
    labels = {Disc.SHORT_RECEIVED: "missing", Disc.REJECTED: "rejected", Disc.EXCESS: "extra"}
    for sku, item in s["po_items"].items():
      line = lines[sku]
      credit = ZERO
      invoice_item = invoice_items.get(item.product_id)
      if invoice_item is not None:
        billable = min(line["accepted"], line["dispatched"])
        credit = invoice_item.line_total - _line_amounts(invoice_item, billable)[2]
      credit_total += credit
      receipt_item = GoodsReceiptItem.objects.create(
        goods_receipt=grn, purchase_order_item=item, ordered_quantity=item.quantity,
        dispatched_quantity=line["dispatched"], received_quantity=line["received"],
        rejected_quantity=line["rejected"], credit_amount=credit,
        note=grn_spec.get("notes", {}).get(sku, ""),
      )
      for kind, qty in (
        (Disc.SHORT_SHIPPED, item.quantity - line["dispatched"]),
        (Disc.SHORT_RECEIVED, line["dispatched"] - line["received"]),
        (Disc.REJECTED, line["rejected"]),
        (Disc.EXCESS, line["received"] - line["dispatched"]),
      ):
        if qty > 0:
          GoodsReceiptDiscrepancy.objects.create(goods_receipt=grn, receipt_item=receipt_item, kind=kind,
                                                 quantity=qty)
          if kind in labels:
            issues.append(f"{item.product_name} ({qty} {labels[kind]})")

    payable = invoice.grand_total - credit_total
    applied = min(po.advance_amount, payable)
    fields = dict(discrepancy_credit=credit_total, advance_applied=applied, balance_due=payable - applied,
                  refund_due=po.advance_amount - applied, updated_at=received_at)
    if payable - applied <= 0:
      fields["status"] = Invoice.Status.PAID
    self.stamp(invoice, **fields)
    self.stamp(po, status=PurchaseOrder.Status.RECEIVED, updated_at=received_at)
    for alert in s["alerts"]:
      self.stamp(alert, status=ReorderSuggestion.Status.CLOSED, updated_at=received_at)
    s["grn_obj"] = grn

    body = f"{self.business.business_name} confirmed delivery of {po.number} ({grn.number})."
    if invoice.discrepancy_credit > 0:
      body += (f" ₹{invoice.discrepancy_credit} was credited on {invoice.number}; "
               f"balance due is now ₹{invoice.balance_due}.")
    else:
      body += f" Balance due on {invoice.number}: ₹{invoice.balance_due}."
    if invoice.refund_due > 0:
      body += f" ₹{invoice.refund_due} of the advance is owed back."
    if issues:
      body += " Issues: " + ", ".join(issues) + "."
    self.notify(po.supplier_profile.user, Kind.PURCHASE_ORDER,
                f"{po.number} was received" + (" (with issues)" if issues else ""), body, received_at)
    if issues:
      self.notify(self.owner, Kind.DISCREPANCY, f"Issues recorded on {grn.number}",
                  ", ".join(issues) + f". ₹{credit_total} was credited on {invoice.number}.", received_at)

    self.settle(s, payable, received_at + timedelta(minutes=5))

  def settle(self, s, payable, when):
    po, invoice = s["po"], s["invoice"]
    advance = po.advance_amount
    if payable >= advance:
      return
    advance_payout = Payout.objects.filter(purchase_order=po, kind=Payout.Kind.ADVANCE).first()
    paid_to_supplier = advance_payout.gross_amount if advance_payout else ZERO
    owed = max(paid_to_supplier - payable, ZERO)
    held = (advance - payable) - owed

    if owed > 0:
      debt = SupplierDebt.objects.create(
        supplier_profile=po.supplier_profile, purchase_order=po, invoice=invoice, amount=owed,
      )
      self.stamp(debt, created_at=when, updated_at=when)
      self.notify(po.supplier_profile.user, Kind.PAYMENT, f"₹{owed} to repay for {po.number}",
                  f"The goods accepted for {po.number} were worth less than the advance you received. "
                  f"₹{owed} will be held back from your next payouts.", when)
    if held > 0 and s.get("advance_payment"):
      self.owner_refund(s["advance_payment"], invoice, OwnerRefund.Source.HELD, held, when)

  def owner_refund(self, payment, invoice, source, amount, when, debt=None, payout=None):
    refund = OwnerRefund.objects.create(
      payment=payment, invoice=invoice, debt=debt, recovered_by=payout, source=source, amount=amount,
      status=OwnerRefund.Status.PROCESSED, razorpay_refund_id=self.rz_id("rfnd"),
    )
    self.stamp(refund, created_at=when, updated_at=when + timedelta(minutes=2))
    self.notify(self.owner, Kind.PAYMENT, f"Refund of ₹{amount} for {invoice.number}",
                "Part of your advance is being refunded to your original payment method "
                "because fewer goods were accepted.", when)

  def make_payout(self, s, kind, gross, when):
    po, invoice = s["po"], s["invoice"]
    supplier = po.supplier_profile
    held, taken = ZERO, []
    for debt in SupplierDebt.objects.filter(supplier_profile=supplier, status=SupplierDebt.Status.OPEN) \
                                    .order_by("created_at"):
      room = gross - held
      if room <= 0:
        break
      part = min(debt.outstanding, room)
      debt.recovered_amount += part
      if debt.recovered_amount >= debt.amount:
        debt.status = SupplierDebt.Status.SETTLED
      debt.save(update_fields=["recovered_amount", "status", "updated_at"])
      self.stamp(debt, updated_at=when)
      held += part
      taken.append((debt, part))
    net = gross - held

    key = next(k for k, p in self.suppliers.items() if p.pk == supplier.pk)
    account = self.payout_accounts.get(key)
    fields = dict(purchase_order=po, invoice=invoice, supplier_profile=supplier, kind=kind,
                  gross_amount=gross, deducted_amount=held, amount=net)
    if net == 0:
      fields.update(status=Payout.Status.PROCESSED, processed_at=when)
    elif account and account.method == SupplierPayoutAccount.Method.UPI and net > Decimal("100000"):
      fields.update(status=Payout.Status.FAILED, attempts=1, failure_reason=(
        "UPI payouts are limited to ₹1,00,000. Add a bank account to receive this amount."))
    elif account:
      if account.method == SupplierPayoutAccount.Method.UPI:
        mode = "UPI"
      else:
        mode = "IMPS" if net <= Decimal("500000") else "NEFT"
      fields.update(
        status=Payout.Status.PROCESSED, mode=mode, razorpay_payout_id=self.rz_id("pout"),
        razorpay_status="processed", fund_account_id=account.razorpay_fund_account_id,
        utr="".join(self.rng.choices(string.digits, k=12)), attempts=1,
        sent_at=when, processed_at=when + timedelta(minutes=4),
      )
    else:
      fields.update(status=Payout.Status.ON_HOLD)
    payout = Payout.objects.create(**fields)
    self.stamp(payout, created_at=when, updated_at=when + timedelta(minutes=4))

    for debt, part in taken:
      payment = Payment.objects.filter(
        purchase_order_id=debt.purchase_order_id, kind=Payment.Kind.ADVANCE, status=Payment.Status.PAID,
      ).first()
      if payment:
        self.owner_refund(payment, debt.invoice, OwnerRefund.Source.RECOVERED, part, when,
                          debt=debt, payout=payout)

    what = "advance" if kind == Payout.Kind.ADVANCE else "balance payment"
    if payout.status == Payout.Status.FAILED:
      self.notify(supplier.user, Kind.PAYMENT, f"Couldn't send ₹{net} for {po.number}",
                  f"{payout.failure_reason} Check your payout details; saving them again retries the payment.",
                  when)
      return payout
    if payout.status == Payout.Status.ON_HOLD:
      self.notify(supplier.user, Kind.PAYMENT, f"Add payout details to receive ₹{net}",
                  f"The {what} for {po.number} is ready to be sent to you. Add your bank account or "
                  "UPI ID in payout settings and we'll send it right away.", when)
      return payout
    deduction = (f" ₹{held} was held back to repay an earlier overpayment." if held > 0 else "")
    if net > 0:
      title = f"₹{net} {what} sent for {po.number}"
      body = f"The {what} for {po.number} has been credited to your account. Bank reference (UTR): {payout.utr}."
    else:
      title, body = f"{po.number} {what} used to repay an overpayment", "Nothing was sent this time."
    self.notify(supplier.user, Kind.PAYMENT, title, body + deduction, when + timedelta(minutes=4))
    self.notify(self.owner, Kind.PAYMENT, f"{what.capitalize()} released to {supplier.company_name}",
                f"₹{gross} for {po.number} was settled with the supplier.", when + timedelta(minutes=4))
    return payout

  def pay_balance(self, s):
    po, invoice = s["po"], s["invoice"]
    invoice.refresh_from_db()
    if invoice.balance_due <= 0:
      return
    paid = self.t(s["balance"])
    amount = invoice.balance_due
    payment = Payment.objects.create(
      purchase_order=po, kind=Payment.Kind.BALANCE, invoice=invoice, amount=amount,
      status=Payment.Status.PAID, razorpay_order_id=self.rz_id("order"),
      razorpay_payment_id=self.rz_id("pay"), paid_at=paid,
    )
    self.stamp(payment, created_at=paid - timedelta(minutes=2), updated_at=paid)
    self.stamp(invoice, status=Invoice.Status.PAID, updated_at=paid)
    self.notify(self.owner, Kind.PAYMENT, f"Balance paid for {invoice.number}",
                f"We received ₹{amount} for {po.number}. It is being sent to "
                f"{po.supplier_profile.company_name}.", paid)
    self.make_payout(s, Payout.Kind.BALANCE, amount, paid + timedelta(minutes=5))

  def close_rfq(self, s):
    rfq = s["rfq"]
    rfq.refresh_from_db()
    if s.get("cancelled"):
      when = self.t(s["cancelled"])
      self.stamp(rfq, status=RFQ.Status.CANCELLED, notes=s.get("cancel_note", rfq.notes), updated_at=when)
      for alert in s["alerts"]:
        self.stamp(alert, status=ReorderSuggestion.Status.CLOSED, rfq=None, updated_at=when)
      for recipient in s["recipients"].values():
        if recipient.status != RFQRecipient.Status.DECLINED:
          self.notify(recipient.supplier_profile.user, Kind.RFQ, f"RFQ {rfq.number} was cancelled",
                      f"{self.business.business_name} cancelled this request for {self.items_label(s)}. "
                      "No quotation is needed.", when)
      return

    deadline_passed = rfq.deadline <= self.now
    if rfq.status == RFQ.Status.OPEN and deadline_passed:
      self.stamp(rfq, status=RFQ.Status.CLOSED, updated_at=rfq.deadline)
    if deadline_passed:
      active = sum(1 for q in s["quotes"].values() if q.status != Quotation.Status.WITHDRAWN)
      if active:
        title = f"Quotations ready for {rfq.number}"
        body = f"{active} quotation(s) received. Compare them and choose a supplier."
      else:
        title, body = f"No quotations for {rfq.number}", "The deadline passed without any quotation."
      self.notify(self.owner, Kind.QUOTATION, title, body, rfq.deadline)

  def finish(self):
    for product in self.products:
      if product.demo["plan"] == "discontinued":
        Product.objects.filter(pk=product.pk).update(is_active=False)
    for outlet in self.outlets:
      if outlet.demo_closed is not None:
        closed = self.at(outlet.demo_closed, 20)
        Outlet.objects.filter(pk=outlet.pk).update(is_active=False, updated_at=closed)

    before = set(ReorderSuggestion.objects.filter(business=self.business).values_list("pk", flat=True))
    create_alerts_for_business(self.business, notify=False)
    new = list(ReorderSuggestion.objects.filter(business=self.business).exclude(pk__in=before)
               .select_related("product"))
    when = self.now - timedelta(hours=1)
    for alert in new:
      self.stamp(alert, created_at=when, updated_at=when)
    if len(new) == 1:
      self.notify(self.owner, Kind.LOW_STOCK, f"{new[0].product.name} is low on stock",
                  f"Only {new[0].product.quantity} left. Create an RFQ to restock.", when)
    elif new:
      names = ", ".join(a.product.name for a in new[:3])
      if len(new) > 3:
        names += f" and {len(new) - 3} more"
      self.notify(self.owner, Kind.LOW_STOCK, f"{len(new)} products are low on stock",
                  f"{names}. Create RFQs to restock.", when)

  def print_summary(self, password):
    business = self.business
    stats = get_dispatch_stats(business)
    low = []
    for product in Product.objects.filter(business=business, is_active=True):
      result = calculate_reorder(product, stats)
      if result.needs_reorder:
        low.append(f"{product.name} (stock {product.quantity}, reorder point {result.reorder_point})")

    out = self.stdout.write
    out(self.style.SUCCESS("Demo data created."))
    out(f"  {Product.objects.filter(business=business).count()} products, "
        f"{Outlet.objects.filter(business=business).count()} outlets, "
        f"{DispatchNote.objects.filter(business=business).count()} dispatch notes, "
        f"{StockMovement.objects.filter(business=business).count()} stock movements, "
        f"{len(SUPPLIERS)} suppliers")
    out(f"  Password for every demo account: {password}")
    out(f"  Owner:     {OWNER_EMAIL}")
    out(f"  Employees: {STAFF_EMAIL}, {STAFF2_EMAIL}")
    out(f"  Invitee:   {INVITEE_EMAIL} (no role yet, has a pending invite)")
    out(f"  Suppliers: demo-supplier-<{'|'.join(s['key'] for s in SUPPLIERS)}>@{DEMO_DOMAIN}")
    out(f"  Low on stock now ({len(low)}):")
    for line in low:
      out(f"    - {line}")

    out(self.style.SUCCESS("Procurement stories:"))
    for s in self.scenarios:
      rfq = RFQ.objects.get(pk=s["rfq"].pk)
      parts = [f"{rfq.number} {rfq.status:<9}", self.items_label(s)[:34].ljust(34)]
      po = s.get("po")
      if po:
        po.refresh_from_db()
        parts.append(f"{po.number} {po.status}")
        invoice = s.get("invoice")
        if invoice:
          invoice.refresh_from_db()
          parts.append(f"{invoice.number} {invoice.status}, balance ₹{invoice.balance_due}")
      out("  " + " | ".join(parts))
    for debt in SupplierDebt.objects.filter(purchase_order__business=business).select_related("purchase_order"):
      out(f"  Supplier debt on {debt.purchase_order.number}: ₹{debt.amount}, "
          f"recovered ₹{debt.recovered_amount} ({debt.status})")
    out("  Payout accounts use placeholder RazorpayX ids. To send a real test payout, log in as the "
        "supplier and save payout details again.")