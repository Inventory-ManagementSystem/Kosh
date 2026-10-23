from rest_framework import serializers

from .models import Quotation


def visible_order(quotation):
  orders = quotation.visible_orders
  return orders[0] if orders else None


class SupplierQuotationStatusSerializer(serializers.ModelSerializer):
  invitation_id = serializers.UUIDField(source="recipient_id", read_only=True)
  rfq_id = serializers.UUIDField(read_only=True)
  rfq_number = serializers.CharField(source="rfq.number", read_only=True)
  business_name = serializers.CharField(source="rfq.business.business_name", read_only=True)
  business_city = serializers.CharField(source="rfq.business.city", read_only=True)
  total_quantity = serializers.IntegerField(read_only=True)
  status = serializers.SerializerMethodField()
  advance_status = serializers.SerializerMethodField()
  order_id = serializers.SerializerMethodField()
  order_number = serializers.SerializerMethodField()
  order_status = serializers.SerializerMethodField()

  class Meta:
    model = Quotation
    fields = [
      "id", "invitation_id", "rfq_id", "rfq_number", "revision",
      "business_name", "business_city",
      "status", "advance_status",
      "order_id", "order_number", "order_status",
      "total_quantity", "grand_total", "advance_amount",
      "delivery_date", "submitted_at", "updated_at",
    ]
    read_only_fields = fields

  def get_status(self, obj):
    if obj.status == Quotation.Status.ACCEPTED and visible_order(obj) is None:
      return Quotation.Status.SUBMITTED.value
    return obj.status

  def get_advance_status(self, obj):
    status = self.get_status(obj)
    if status == Quotation.Status.ACCEPTED:
      return "not_required" if obj.advance_amount == 0 else "paid"
    if status == Quotation.Status.SUBMITTED:
      return "pending"
    return None

  def get_order_id(self, obj):
    order = visible_order(obj)
    return str(order.pk) if order else None

  def get_order_number(self, obj):
    order = visible_order(obj)
    return order.number if order else None

  def get_order_status(self, obj):
    order = visible_order(obj)
    return order.status if order else None
