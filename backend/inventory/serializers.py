from rest_framework import serializers
from .models import Category, Product, Warehouse


def get_business(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    if user and user.is_authenticated and hasattr(user, "business"):
        return user.business
    return None


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
        queryset=Warehouse.objects.none(),
        required=False,
        allow_null=True,
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
    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "sku",
            "description",
            "category",
            "category_name",
            "warehouse",
            "warehouse_name",
            "price",
            "cost_price",
            "quantity",
            "low_stock_threshold",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
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
            self.fields["warehouse"].queryset = (
                Warehouse.objects.filter(
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
        if self.instance is not None and "quantity" in attrs:
            raise serializers.ValidationError({
                "quantity": (
                    "Use the adjust-stock endpoint "
                    "to change stock."
                )
            })

        return attrs


class StockAdjustmentSerializer(serializers.Serializer):
    change = serializers.IntegerField(
        min_value=-1_000_000,
        max_value=1_000_000,
    )
    reason = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )

    def validate_change(self, value):
        if value == 0:
            raise serializers.ValidationError(
                "Change cannot be zero."
            )
        return value


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