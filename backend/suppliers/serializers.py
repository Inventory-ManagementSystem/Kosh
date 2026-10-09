import re

from rest_framework import serializers
from accounts.validators import validate_phone_number
from .models import SupplierProfile, SupplyCategory


GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$") 

class SupplyCategorySerializer(serializers.ModelSerializer):
  class Meta:
    model = SupplyCategory
    fields = ["id", "name"]


class SupplierProfileSerializer(serializers.ModelSerializer):
  categories = serializers.PrimaryKeyRelatedField(
    many=True,
    allow_empty=False,
    queryset=SupplyCategory.objects.filter(is_active=True),
  )
  category_names = serializers.SlugRelatedField(
    source="categories",
    many=True,
    read_only=True,
    slug_field="name",
  )
  email = serializers.EmailField(source="user.email", read_only=True)
  gstin = serializers.CharField(max_length=15)

  class Meta:
    model = SupplierProfile
    fields = [
      "id",
      "company_name",
      "email",
      "phone",
      "gstin",
      "address",
      "city",
      "pincode",
      "categories",
      "category_names",
      "is_verified",
      "verified_at",
      "created_at",
      "updated_at",
    ]
    read_only_fields = [
      "id",
      "is_verified",
      "verified_at",
      "created_at",
      "updated_at",
    ]

  def validate_company_name(self, value):
    value = " ".join(value.split())
    if not value:
      raise serializers.ValidationError("Company name cannot be empty.")
    return value

  def validate_phone(self, value):
    value = validate_phone_number(re.sub(r"[\s-]", "", value))
    if not value:
      raise serializers.ValidationError("Phone number is required.")
    return value

  def validate_city(self, value):
    value = " ".join(value.split())
    if not value:
      raise serializers.ValidationError("City cannot be empty.")
    return value

  def validate_gstin(self, value):
    value = value.strip().upper()
    if not GSTIN_REGEX.fullmatch(value):
      raise serializers.ValidationError("Enter a valid 15-character GSTIN.")
    taken = SupplierProfile.objects.filter(gstin=value)
    if self.instance is not None:
      taken = taken.exclude(pk=self.instance.pk)
    if taken.exists():
      raise serializers.ValidationError("This GSTIN is already registered to another supplier.")
    return value

  def update(self, instance, validated_data):
    identity_changed = any(
      field in validated_data and validated_data[field] != getattr(instance, field)
      for field in ("company_name", "gstin")
    )
    if instance.is_verified and identity_changed:
      instance.is_verified = False
      instance.verified_at = None
    return super().update(instance, validated_data)