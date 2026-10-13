from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import RFQ, RFQItem, RFQRecipient, ReorderSuggestion


def _category_name(product):
  return product.category.name if product.category else None


class RFQItemSerializer(serializers.ModelSerializer):
  category = serializers.SerializerMethodField()

  class Meta:
    model = RFQItem
    fields = ["id", "product", "product_name", "sku", "category", "quantity"]
    read_only_fields = fields

  def get_category(self, obj):
    return _category_name(obj.product)


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
  product_name = serializers.SerializerMethodField()
  sku = serializers.SerializerMethodField()
  category = serializers.SerializerMethodField()
  quantity = serializers.SerializerMethodField()  # quantity to order ("Stock size" on the card)
  expected_delivery = serializers.SerializerMethodField()
  recipient_count = serializers.SerializerMethodField()
  quoted_count = serializers.SerializerMethodField()
  auto_generated = serializers.SerializerMethodField()

  class Meta:
    model = RFQ
    fields = [
      "id", "number", "status", "deadline", "include_platform_pool",
      "auto_generated", "product_name", "sku", "category", "quantity",
      "expected_delivery", "recipient_count", "quoted_count", "created_at",
    ]
    read_only_fields = fields

  def _first_item(self, obj):
    items = list(obj.items.all())
    return items[0] if items else None

  def get_product_name(self, obj):
    item = self._first_item(obj)
    return item.product_name if item else None

  def get_sku(self, obj):
    item = self._first_item(obj)
    return item.sku if item else None

  def get_category(self, obj):
    item = self._first_item(obj)
    return _category_name(item.product) if item else None

  def get_quantity(self, obj):
    item = self._first_item(obj)
    return item.quantity if item else None

  def get_expected_delivery(self, obj):
    item = self._first_item(obj)
    if item is None:
      return None
    return obj.created_at.date() + timedelta(days=item.product.lead_time_days)

  def get_recipient_count(self, obj):
    return len(obj.recipients.all())

  def get_quoted_count(self, obj):
    return sum(1 for r in obj.recipients.all() if r.status == RFQRecipient.Status.QUOTED)

  def get_auto_generated(self, obj):
    return obj.created_by_id is None


class RFQDetailSerializer(RFQListSerializer):
  items = RFQItemSerializer(many=True, read_only=True)
  recipients = RFQRecipientSerializer(many=True, read_only=True)
  reorder_suggestion_id = serializers.UUIDField(read_only=True)

  class Meta(RFQListSerializer.Meta):
    fields = RFQListSerializer.Meta.fields + [
      "notes", "reorder_suggestion_id", "items", "recipients", "updated_at",
    ]
    read_only_fields = fields


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
  category = serializers.SerializerMethodField()
  required_stock = serializers.IntegerField(source="suggested_quantity", read_only=True)
  stock_status = serializers.CharField(source="product.status", read_only=True)  # "Low Stock" / "Out of Stock"

  class Meta:
    model = ReorderSuggestion
    fields = [
      "id", "product_id", "product_name", "sku", "category",
      "required_stock", "stock_status", "status", "created_at",
    ]
    read_only_fields = fields

  def get_category(self, obj):
    return _category_name(obj.product)


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
  deadline = serializers.DateTimeField(source="rfq.deadline", read_only=True)
  rfq_status = serializers.CharField(source="rfq.status", read_only=True)
  my_status = serializers.CharField(source="status", read_only=True)
  item_count = serializers.SerializerMethodField()

  class Meta:
    model = RFQRecipient
    fields = [
      "id", "rfq_id", "number", "business_name", "business_city",
      "deadline", "rfq_status", "my_status", "item_count", "created_at",
    ]
    read_only_fields = fields

  def get_item_count(self, obj):
    return len(obj.rfq.items.all())


class SupplierRFQDetailSerializer(SupplierRFQListSerializer):
  notes = serializers.CharField(source="rfq.notes", read_only=True)
  items = SupplierRFQItemSerializer(source="rfq.items", many=True, read_only=True)

  class Meta(SupplierRFQListSerializer.Meta):
    fields = SupplierRFQListSerializer.Meta.fields + ["notes", "items"]
    read_only_fields = fields
