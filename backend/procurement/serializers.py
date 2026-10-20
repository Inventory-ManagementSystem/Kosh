from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import RFQ, Quotation, QuotationItem, RFQItem, RFQRecipient, ReorderSuggestion, PurchaseOrder
from .services import calculate_totals
from .models import Payment




class RFQItemSerializer(serializers.ModelSerializer):
  category = serializers.CharField(source="product.display_category", read_only=True)
  supply_category = serializers.CharField(
    source="product.supply_category.name", read_only=True, default=None
  )

  class Meta:
    model = RFQItem
    fields = ["id", "product", "product_name", "sku", "category", "quantity", "supply_category"]
    read_only_fields = fields




class RFQRecipientSerializer(serializers.ModelSerializer):
  supplier_profile_id = serializers.UUIDField(read_only=True)
  company_name = serializers.CharField(source="supplier_profile.company_name", read_only=True)
  city = serializers.CharField(source="supplier_profile.city", read_only=True)

  class Meta:
    model = RFQRecipient
    fields = [
      "id", "supplier_profile_id", "company_name", "city",
      "source", "status", "viewed_at", "responded_at",
    ]
    read_only_fields = fields


class RFQListSerializer(serializers.ModelSerializer):
  supply_category = serializers.SerializerMethodField()
  items = RFQItemSerializer(many=True, read_only=True)
  item_count = serializers.SerializerMethodField()
  total_quantity = serializers.SerializerMethodField()
  expected_delivery = serializers.SerializerMethodField()
  recipient_count = serializers.SerializerMethodField()
  quoted_count = serializers.SerializerMethodField()
  auto_generated = serializers.SerializerMethodField()

  class Meta:
    model = RFQ
    fields = [
      "id", "number", "status", "deadline", "include_platform_pool",
      "auto_generated", "supply_category", "item_count", "total_quantity", "items",
      "expected_delivery", "recipient_count", "quoted_count", "created_at",
    ]
    read_only_fields = fields

  def get_supply_category(self, obj):
    return obj.supply_category.name if obj.supply_category_id else None

  def get_item_count(self, obj):
    return len(obj.items.all())

  def get_total_quantity(self, obj):
    return sum(item.quantity for item in obj.items.all())

  def get_expected_delivery(self, obj):
    return rfq_expected_delivery(obj)

  def get_recipient_count(self, obj):
    return len(obj.recipients.all())

  def get_quoted_count(self, obj):
    return sum(1 for r in obj.recipients.all() if r.status == RFQRecipient.Status.QUOTED)

  def get_auto_generated(self, obj):
    return obj.created_by_id is None


class RFQDetailSerializer(RFQListSerializer):
  recipients = RFQRecipientSerializer(many=True, read_only=True)
  reorder_suggestion_ids = serializers.SerializerMethodField()

  class Meta(RFQListSerializer.Meta):
    fields = RFQListSerializer.Meta.fields + [
      "notes", "reorder_suggestion_ids", "recipients", "updated_at",
    ]
    read_only_fields = fields

  def get_reorder_suggestion_ids(self, obj):
    return [s.id for s in obj.reorder_suggestions.all()]


class RFQUpdateSerializer(serializers.ModelSerializer):
  class Meta:
    model = RFQ
    fields = ["deadline", "notes"]

  def validate_deadline(self, value):
    if value <= timezone.now():
      raise serializers.ValidationError("Deadline must be in the future.")
    return value

  def validate(self, attrs):
    if self.instance and self.instance.status != RFQ.Status.OPEN:
      raise serializers.ValidationError("Only an open RFQ can be edited.")
    return attrs


class ReorderAlertSerializer(serializers.ModelSerializer):
  product_id = serializers.UUIDField(read_only=True)
  product_name = serializers.CharField(source="product.name", read_only=True)
  sku = serializers.CharField(source="product.sku", read_only=True)
  category = serializers.CharField(source="product.display_category", read_only=True)
  supply_category = serializers.CharField(
    source="product.supply_category.name", read_only=True, default=None
  )
  supply_category_id = serializers.IntegerField(
    source="product.supply_category_id", read_only=True
  )
  required_stock = serializers.IntegerField(source="suggested_quantity", read_only=True)
  stock_status = serializers.CharField(source="product.status", read_only=True)
  price = serializers.DecimalField(
    source="product.price", max_digits=12, decimal_places=2, read_only=True
  )
  cost_price = serializers.DecimalField(
    source="product.cost_price", max_digits=12, decimal_places=2, read_only=True
  )
  rfq_id = serializers.UUIDField(read_only=True)


  class Meta:
    model = ReorderSuggestion
    fields = [
      "id", "product_id", "product_name", "sku", "category", "supply_category", "supply_category_id",
      "required_stock", "price", "cost_price", "stock_status", "method", "status", "rfq_id", "created_at",
    ]
    read_only_fields = fields




class SupplierRFQItemSerializer(serializers.ModelSerializer):
  class Meta:
    model = RFQItem
    fields = ["id", "product_name", "sku", "quantity"]
    read_only_fields = fields


class SupplierRFQListSerializer(serializers.ModelSerializer):
  rfq_id = serializers.UUIDField(read_only=True)
  number = serializers.CharField(source="rfq.number", read_only=True)
  business_name = serializers.CharField(source="rfq.business.business_name", read_only=True)
  business_city = serializers.CharField(source="rfq.business.city", read_only=True)
  supply_category = serializers.SerializerMethodField()
  deadline = serializers.DateTimeField(source="rfq.deadline", read_only=True)
  rfq_status = serializers.CharField(source="rfq.status", read_only=True)
  my_status = serializers.CharField(source="status", read_only=True)
  item_count = serializers.SerializerMethodField()
  total_quantity = serializers.SerializerMethodField()

  class Meta:
    model = RFQRecipient
    fields = [
      "id", "rfq_id", "number", "business_name", "business_city", "supply_category",
      "deadline", "rfq_status", "my_status", "item_count", "total_quantity", "created_at",
    ]
    read_only_fields = fields

  def get_supply_category(self, obj):
    category = obj.rfq.supply_category
    return category.name if category else None

  def get_item_count(self, obj):
    return len(obj.rfq.items.all())

  def get_total_quantity(self, obj):
    return sum(item.quantity for item in obj.rfq.items.all())


class SupplierRFQDetailSerializer(SupplierRFQListSerializer):
  notes = serializers.CharField(source="rfq.notes", read_only=True)
  items = SupplierRFQItemSerializer(source="rfq.items", many=True, read_only=True)

  class Meta(SupplierRFQListSerializer.Meta):
    fields = SupplierRFQListSerializer.Meta.fields + ["notes", "items"]
    read_only_fields = fields



def rfq_expected_delivery(rfq):
  items = list(rfq.items.all())
  if not items:
    return None
  lead_days = max(item.product.lead_time_days for item in items)
  return rfq.created_at.date() + timedelta(days=lead_days)


class QuotationItemInputSerializer(serializers.Serializer):
  rfq_item = serializers.UUIDField()
  quantity = serializers.IntegerField(min_value=1, required=False)
  unit_price = serializers.DecimalField(
    max_digits=12, decimal_places=2, min_value=Decimal("0.01")
  )
  gst_rate = serializers.DecimalField(
    max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("40"),
    default=Decimal("0"),
  )


class QuotationSubmitSerializer(serializers.Serializer):
  items = QuotationItemInputSerializer(many=True, allow_empty=False)
  advance_amount = serializers.DecimalField(
    max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
  )
  delivery_date = serializers.DateField()
  valid_until = serializers.DateField(required=False)
  notes = serializers.CharField(
    max_length=2000, required=False, allow_blank=True, default=""
  )

  def validate_notes(self, value):
    return value.strip()

  def validate_delivery_date(self, value):
    if value < timezone.localdate():
      raise serializers.ValidationError("Delivery date cannot be in the past.")
    return value

  def validate_valid_until(self, value):
    deadline_date = timezone.localdate(self.context["rfq"].deadline)
    if value < deadline_date:
      raise serializers.ValidationError(
        f"Quotation must stay valid at least until the RFQ deadline ({deadline_date})."
      )
    return value

  def validate_items(self, items):
    rfq_items = {item.id: item for item in self.context["rfq"].items.all()}
    seen = set()
    for line in items:
      item = rfq_items.get(line["rfq_item"])
      if item is None:
        raise serializers.ValidationError(
          f"Item {line['rfq_item']} is not part of this RFQ."
        )
      if item.id in seen:
        raise serializers.ValidationError("Each RFQ item can be quoted only once.")
      seen.add(item.id)

      quantity = line.get("quantity", item.quantity)
      if quantity != item.quantity:
        raise serializers.ValidationError(
          f"Quote the full quantity: {item.quantity} units of {item.product_name}."
        )
      line["rfq_item"] = item
      line["quantity"] = item.quantity

    missing = sorted(i.product_name for i in rfq_items.values() if i.id not in seen)
    if missing:
      raise serializers.ValidationError(
        "Quote every product on this RFQ. Missing: " + ", ".join(missing) + "."
      )
    return items

  def validate(self, attrs):
    _, _, grand_total = calculate_totals(attrs["items"])
    if attrs["advance_amount"] > grand_total:
      raise serializers.ValidationError({
        "advance_amount": [f"Advance payment cannot exceed the total amount (₹{grand_total})."],
      })
    return attrs


class QuotationItemSerializer(serializers.ModelSerializer):
  rfq_item_id = serializers.UUIDField(read_only=True)
  product_name = serializers.CharField(source="rfq_item.product_name", read_only=True)
  sku = serializers.CharField(source="rfq_item.sku", read_only=True)
  requested_quantity = serializers.IntegerField(source="rfq_item.quantity", read_only=True)

  class Meta:
    model = QuotationItem
    fields = [
      "id", "rfq_item_id", "product_name", "sku", "requested_quantity",
      "quantity", "unit_price", "gst_rate", "line_subtotal", "line_tax", "line_total",
    ]
    read_only_fields = fields


QUOTATION_FIELDS = [
  "id", "status", "revision", "items",
  "subtotal", "tax_total", "grand_total", "advance_amount", "balance_amount",
  "delivery_date", "expected_delivery", "is_late", "late_by_days",
  "valid_until", "notes", "submitted_at", "updated_at",
]


class QuotationSerializer(serializers.ModelSerializer):
  items = QuotationItemSerializer(many=True, read_only=True)
  balance_amount = serializers.SerializerMethodField()
  expected_delivery = serializers.SerializerMethodField()
  is_late = serializers.SerializerMethodField()
  late_by_days = serializers.SerializerMethodField()

  class Meta:
    model = Quotation
    fields = QUOTATION_FIELDS
    read_only_fields = fields

  def get_balance_amount(self, obj):
    return str(obj.grand_total - obj.advance_amount)

  def get_expected_delivery(self, obj):
    return rfq_expected_delivery(obj.rfq)

  def get_late_by_days(self, obj):
    expected = rfq_expected_delivery(obj.rfq)
    if expected is None or obj.delivery_date <= expected:
      return 0
    return (obj.delivery_date - expected).days

  def get_is_late(self, obj):
    return self.get_late_by_days(obj) > 0


class OwnerQuotationSerializer(QuotationSerializer):
  supplier_profile_id = serializers.UUIDField(read_only=True)
  company_name = serializers.CharField(source="supplier_profile.company_name", read_only=True)
  city = serializers.CharField(source="supplier_profile.city", read_only=True)
  supplier_verified = serializers.BooleanField(source="supplier_profile.is_verified", read_only=True)
  source = serializers.CharField(source="recipient.source", read_only=True)
  rank = serializers.SerializerMethodField()
  score = serializers.SerializerMethodField()
  breakdown = serializers.SerializerMethodField()
  badges = serializers.SerializerMethodField()

  class Meta(QuotationSerializer.Meta):
    fields = QUOTATION_FIELDS + [
      "supplier_profile_id", "company_name", "city", "supplier_verified", "source",
      "rank", "score", "breakdown", "badges",
    ]
    read_only_fields = fields

  def _info(self, obj):
    return self.context.get("ranking", {}).get(obj.pk)

  def get_rank(self, obj):
    info = self._info(obj)
    return info["rank"] if info else None

  def get_score(self, obj):
    info = self._info(obj)
    return info["score"] if info else None

  def get_breakdown(self, obj):
    info = self._info(obj)
    return info["breakdown"] if info else None

  def get_badges(self, obj):
    info = self._info(obj)
    return info["badges"] if info else []


class SupplierRFQInboxDetailSerializer(SupplierRFQDetailSerializer):
  expected_delivery = serializers.SerializerMethodField()
  can_quote = serializers.SerializerMethodField()
  my_quotation = serializers.SerializerMethodField()

  class Meta(SupplierRFQDetailSerializer.Meta):
    fields = SupplierRFQDetailSerializer.Meta.fields + [
      "expected_delivery", "can_quote", "my_quotation",
    ]
    read_only_fields = fields

  def get_expected_delivery(self, obj):
    return rfq_expected_delivery(obj.rfq)

  def get_can_quote(self, obj):
    return obj.rfq.status == RFQ.Status.OPEN and obj.rfq.deadline > timezone.now()

  def get_my_quotation(self, obj):
    try:
      quotation = obj.quotation
    except Quotation.DoesNotExist:
      return None
    quotation.rfq = obj.rfq
    return QuotationSerializer(quotation).data

class RFQCreateSerializer(serializers.Serializer):
  quantity = serializers.IntegerField(required=False, min_value=1, max_value=1_000_000)
  include_platform_pool = serializers.BooleanField(required=False, default=False)

class AlertSelectionSerializer(serializers.Serializer):
  id = serializers.UUIDField()
  quantity = serializers.IntegerField(required=False, min_value=1, max_value=1_000_000)


class BulkRFQCreateSerializer(serializers.Serializer):
  alerts = AlertSelectionSerializer(many=True, allow_empty=False)
  include_platform_pool = serializers.BooleanField(required=False, default=False)

  def validate_alerts(self, alerts):
    if len(alerts) > 50:
      raise serializers.ValidationError("You can select at most 50 alerts at a time.")
    ids = [a["id"] for a in alerts]
    if len(ids) != len(set(ids)):
      raise serializers.ValidationError("Each alert can be selected only once.")
    return alerts

class PurchaseOrderSummarySerializer(serializers.ModelSerializer):
  rfq_id = serializers.UUIDField(read_only=True)
  rfq_number = serializers.CharField(source="rfq.number", read_only=True)
  quotation_id = serializers.UUIDField(read_only=True)
  supplier_profile_id = serializers.UUIDField(read_only=True)
  company_name = serializers.CharField(source="supplier_profile.company_name", read_only=True)
  balance_amount = serializers.SerializerMethodField()
 
  class Meta:
    model = PurchaseOrder
    fields = [
      "id", "number", "status", "rfq_id", "rfq_number", "quotation_id",
      "supplier_profile_id", "company_name",
      "subtotal", "tax_total", "grand_total", "advance_amount", "balance_amount",
      "delivery_date", "advance_due_by", "issued_at", "created_at",
    ]
    read_only_fields = fields
 
  def get_balance_amount(self, obj):
    return str(obj.balance_amount)


class PaymentSerializer(serializers.ModelSerializer):
  class Meta:
    model = Payment
    fields = [
      "id", "amount", "status", "razorpay_order_id", "razorpay_payment_id",
      "failure_reason", "refund_id", "paid_at", "created_at",
    ]
    read_only_fields = fields


class AdvanceVerifySerializer(serializers.Serializer):
  razorpay_order_id = serializers.CharField(max_length=64)
  razorpay_payment_id = serializers.CharField(max_length=64)
  razorpay_signature = serializers.CharField(max_length=128)
