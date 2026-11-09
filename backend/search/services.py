from django.db.models import Case, IntegerField, Q, Value, When

from inventory.models import Product
from procurement.models import GoodsReceipt, Invoice, PurchaseOrder, RFQ
from suppliers.models import Supplier

MIN_QUERY_LENGTH = 3
MAX_QUERY_LENGTH = 50
LIMIT_PER_TYPE = 5

EMPTY_RESULT = {
  "products": [], "suppliers": [], "rfqs": [],
  "purchase_orders": [], "invoices": [], "goods_receipts": [],
}


def item(obj_id, kind, title, subtitle=""):
  return {"id": str(obj_id), "type": kind, "title": title, "subtitle": subtitle}


def top(qs, term, fields, tiebreak):
  starts = Q()
  for field in fields:
    starts |= Q(**{f"{field}__istartswith": term})
  rank = Case(When(starts, then=Value(0)), default=Value(1), output_field=IntegerField())
  return qs.annotate(rank=rank).order_by("rank", tiebreak)[:LIMIT_PER_TYPE]


def search_products(business, term):
  qs = (
    Product.objects.filter(business=business, is_active=True)
    .filter(Q(name__icontains=term) | Q(sku__icontains=term))
    .only("id", "name", "sku", "quantity", "low_stock_threshold")
  )
  return [
    item(p.id, "product", p.name, f"{p.sku} · {p.status} ({p.quantity})")
    for p in top(qs, term, ["name", "sku"], "name")
  ]


def search_suppliers(business, term):
  qs = (
    Supplier.objects.filter(business=business, is_active=True)
    .select_related("linked_account")
    .filter(
      Q(email__icontains=term)
      | Q(label__icontains=term)
      | Q(linked_account__company_name__icontains=term)
    )
    .only("id", "email", "label", "linked_account", "linked_account__company_name")
  )
  results = []
  fields = ["email", "label", "linked_account__company_name"]
  for s in top(qs, term, fields, "email"):
    profile = s.linked_account
    title = profile.company_name if profile else (s.label or s.email)
    results.append(item(s.id, "supplier", title, s.email))
  return results


def search_rfqs(business, term):
  qs = (
    RFQ.objects.filter(business=business)
    .select_related("supply_category")
    .filter(Q(number__icontains=term) | Q(supply_category__name__icontains=term))
    .only("id", "number", "status", "supply_category", "supply_category__name")
  )
  results = []
  for r in top(qs, term, ["number", "supply_category__name"], "-created_at"):
    category = r.supply_category.name if r.supply_category else "No category"
    results.append(item(r.id, "rfq", r.number, f"{category} · {r.get_status_display()}"))
  return results


def search_purchase_orders(business, term):
  qs = (
    PurchaseOrder.objects.filter(business=business)
    .select_related("supplier_profile")
    .filter(Q(number__icontains=term) | Q(supplier_profile__company_name__icontains=term))
    .only("id", "number", "status", "supplier_profile", "supplier_profile__company_name")
  )
  return [
    item(
      po.id, "purchase_order", po.number,
      f"{po.supplier_profile.company_name} · {po.get_status_display()}",
    )
    for po in top(qs, term, ["number", "supplier_profile__company_name"], "-created_at")
  ]


def search_invoices(business, term):
  qs = (
    Invoice.objects.filter(business=business)
    .select_related("supplier_profile")
    .filter(Q(number__icontains=term) | Q(supplier_profile__company_name__icontains=term))
    .only("id", "number", "status", "supplier_profile", "supplier_profile__company_name")
  )
  return [
    item(
      inv.id, "invoice", inv.number,
      f"{inv.supplier_profile.company_name} · {inv.get_status_display()}",
    )
    for inv in top(qs, term, ["number", "supplier_profile__company_name"], "-created_at")
  ]


def search_receipts(business, term):
  qs = (
    GoodsReceipt.objects.filter(business=business)
    .select_related("purchase_order")
    .filter(Q(number__icontains=term) | Q(purchase_order__number__icontains=term))
    .only("id", "number", "purchase_order", "purchase_order__number")
  )
  return [
    item(g.id, "goods_receipt", g.number, f"For {g.purchase_order.number}")
    for g in top(qs, term, ["number", "purchase_order__number"], "-created_at")
  ]


def global_search(business, raw_query):
  term = (raw_query or "").strip()[:MAX_QUERY_LENGTH]
  if len(term) < MIN_QUERY_LENGTH:
    return {key: [] for key in EMPTY_RESULT}
  return {
    "products": search_products(business, term),
    "suppliers": search_suppliers(business, term),
    "rfqs": search_rfqs(business, term),
    "purchase_orders": search_purchase_orders(business, term),
    "invoices": search_invoices(business, term),
    "goods_receipts": search_receipts(business, term),
  }
