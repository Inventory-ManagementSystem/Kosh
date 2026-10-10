from rest_framework import serializers
from .models import (
    Category, Product, Warehouse, DispatchItem, DispatchNote, Outlet,
)
from django.utils import timezone

QUANTITY_ERROR = "Stock can't be set here. Use the adjust-stock endpoint."

def get_business(context):
    request = context.get("request")
    return getattr(request, "business", None)


def clean_name(value):
    value = " ".join(value.split())
    if not value:
        raise serializers.ValidationError(
            "Name cannot be empty."
        )
    return value

def check_name_is_unique(
    model,
    business,
    name,
    instance,
    model_name,
    ):
    queryset = model.objects.filter(
        business=business,
        name__iexact=name,
    )
    if instance:
        queryset = queryset.exclude(
            pk=instance.pk
        )
    if queryset.exists():
        raise serializers.ValidationError(
            f"{model_name} with this name already exists."
        )

class ProductSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.none(),
        required=False,
        allow_null=True,
    )
    warehouse = serializers.PrimaryKeyRelatedField(
        read_only=True,
    )
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
        default=None,
    )
    warehouse_name = serializers.CharField(
        source="warehouse.name",
        read_only=True,
        default=None,
    )
    status = serializers.CharField(
        read_only=True
    )

    opening_quantity = serializers.IntegerField(
        write_only=True,
        required=False,
        min_value=0,
        max_value=1_000_000,
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "image",
            "sku",
            "description",
            "category",
            "category_name",
            "warehouse",
            "warehouse_name",
            "price",
            "cost_price",
            "quantity",
            "opening_quantity",
            "low_stock_threshold",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "quantity",
            "status",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        business = get_business(self.context)
        if business:
            self.fields["category"].queryset = (
                Category.objects.filter(
                    business=business
                )
            )

    def validate_name(self, value):
        return clean_name(value)
    
    def validate_sku(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError(
                "SKU cannot be empty."
            )
        business = get_business(self.context)
        others = Product.objects.filter(
            business=business,
            sku=value,
        )
        if self.instance:
            others = others.exclude(
                pk=self.instance.pk
            )
        if others.exists():
            raise serializers.ValidationError(
                "SKU already exists in your inventory."
            )
        return value

    def validate(self, attrs):
        if "quantity" in self.initial_data:
            raise serializers.ValidationError({
                "quantity": QUANTITY_ERROR
            })
        if self.instance and "opening_quantity" in self.initial_data:
            raise serializers.ValidationError({
                "opening_quantity": "Opening stock can only be set when creating a product."
            })

        return attrs


class StockAdjustmentSerializer(serializers.Serializer):
    change = serializers.IntegerField(min_value=-1_000_000, max_value=1_000_000)
    reason = serializers.ChoiceField(choices=["adjustment", "damaged"], default="adjustment")
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_change(self, value):
        if value == 0:
            raise serializers.ValidationError("Change cannot be zero.")
        return value

    def validate(self, attrs):
        if attrs["reason"] == "damaged" and attrs["change"] > 0:
            raise serializers.ValidationError(
                {"change": "Damaged stock must be a negative change."}
            )
        return attrs


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        value = clean_name(value)
        business = get_business(self.context)
        check_name_is_unique(
            Category,
            business,
            value,
            self.instance,
            "Category",
        )
        return value


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id",
            "name",
            "address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        return clean_name(value)

class OutletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Outlet
        fields = ["id", "name", "address", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = clean_name(value)
        check_name_is_unique(
            Outlet, get_business(self.context), value, self.instance, "Outlet"
        )
        return value


class DispatchItemInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.none())
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)


class DispatchCreateSerializer(serializers.Serializer):
    outlet = serializers.PrimaryKeyRelatedField(queryset=Outlet.objects.none())
    dispatch_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    items = DispatchItemInputSerializer(many=True, allow_empty=False, max_length=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        business = get_business(self.context)
        if business:
            self.fields["outlet"].queryset = Outlet.objects.filter(
                business=business, is_active=True
            )
            self.fields["items"].child.fields["product"].queryset = (
                Product.objects.filter(business=business)
            )

    def validate_dispatch_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Dispatch date cannot be in the future.")
        return value


class DispatchItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = DispatchItem
        fields = ["id", "product", "product_name", "product_sku", "quantity"]


class DispatchNoteSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)
    created_by_email = serializers.CharField(
        source="created_by.email", read_only=True, default=None
    )
    items = DispatchItemSerializer(many=True, read_only=True)

    class Meta:
        model = DispatchNote
        fields = [
            "id", "number", "outlet", "outlet_name", "dispatch_date",
            "notes", "created_by_email", "items", "created_at",
        ]
