import re

from rest_framework import serializers
from accounts.validators import validate_phone_number
from .models import SupplierProfile, SupplyCategory, Supplier, SupplierPayoutAccount


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
    lost_verification = instance.is_verified and identity_changed
    if lost_verification:
      instance.is_verified = False
      instance.verified_at = None
    instance = super().update(instance, validated_data)
    if lost_verification:
      from notifications import events
      events.supplier_unverified(instance)
    return instance

class OwnerSupplierSerializer(serializers.ModelSerializer):
  display_name = serializers.SerializerMethodField()
  status = serializers.SerializerMethodField()
  company_name = serializers.SerializerMethodField()
  city = serializers.SerializerMethodField()
  pincode = serializers.SerializerMethodField()
  category_names = serializers.SerializerMethodField()
  account_verified = serializers.SerializerMethodField()

  class Meta:
    model = Supplier
    fields = [
      "id", "email", "phone", "label", "is_active",
      "display_name", "status", "company_name", "city", "pincode",
      "category_names", "account_verified", "created_at", "updated_at",
    ]
    read_only_fields = ["id", "created_at", "updated_at"]

  def _profile(self, obj):
    return obj.linked_account if obj.linked_account_id else None

  def get_status(self, obj):
    return "linked" if obj.linked_account_id else "invited"

  def get_display_name(self, obj):
    profile = self._profile(obj)
    return profile.company_name if profile else (obj.label or obj.email)

  def get_company_name(self, obj):
    profile = self._profile(obj)
    return profile.company_name if profile else None

  def get_city(self, obj):
    profile = self._profile(obj)
    return profile.city if profile else None

  def get_pincode(self, obj):
    profile = self._profile(obj)
    return profile.pincode if profile else None

  def get_category_names(self, obj):
    profile = self._profile(obj)
    return [c.name for c in profile.categories.all()] if profile else []

  def get_account_verified(self, obj):
    profile = self._profile(obj)
    return bool(profile and profile.is_verified)

  def validate_email(self, value):
      value = value.strip().lower()
      business = self.context["request"].business
      taken = Supplier.objects.filter(business=business, email__iexact=value)
      if self.instance is not None:
        taken = taken.exclude(pk=self.instance.pk)
      if taken.exists():
        raise serializers.ValidationError("This supplier is already in your list.")
      return value

  def update(self, instance, validated_data):
    if "email" in validated_data and validated_data["email"] != instance.email:
      validated_data["linked_account"] = SupplierProfile.objects.filter(
        user__email__iexact=validated_data["email"]
      ).first()
    return super().update(instance, validated_data)

  def validate_phone(self, value):
    if not value:
      return value
    return validate_phone_number(re.sub(r"[\s-]", "", value))

  def validate_label(self, value):
    return " ".join(value.split())

  def create(self, validated_data):
    validated_data["linked_account"] = SupplierProfile.objects.filter(
      user__email__iexact=validated_data["email"]
    ).first()
    return super().create(validated_data)

IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
VPA_REGEX = re.compile(r"^[A-Za-z0-9.\-]+@[A-Za-z0-9.\-]+$")


class PayoutAccountInputSerializer(serializers.Serializer):
  method = serializers.ChoiceField(choices=SupplierPayoutAccount.Method.choices)
  account_holder_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
  ifsc = serializers.CharField(max_length=11, required=False, allow_blank=True)
  account_number = serializers.CharField(max_length=24, required=False, allow_blank=True)
  account_number_confirm = serializers.CharField(max_length=24, required=False, allow_blank=True)
  vpa = serializers.CharField(max_length=100, required=False, allow_blank=True)

  def validate(self, attrs):
    method = attrs["method"]
    if method == SupplierPayoutAccount.Method.BANK_ACCOUNT:
      errors = {}
      name = " ".join((attrs.get("account_holder_name") or "").split())
      if len(name) < 3:
        errors["account_holder_name"] = ["Enter the name on the bank account."]
      ifsc = (attrs.get("ifsc") or "").strip().upper()
      if not IFSC_REGEX.match(ifsc):
        errors["ifsc"] = ["Enter a valid 11-character IFSC, e.g. HDFC0001234."]
      number = re.sub(r"\s", "", attrs.get("account_number") or "")
      confirm = re.sub(r"\s", "", attrs.get("account_number_confirm") or "")
      if not re.fullmatch(r"[0-9]{9,18}", number):
        errors["account_number"] = ["Enter a valid account number (9 to 18 digits)."]
      elif confirm != number:
        errors["account_number_confirm"] = ["The account numbers don't match."]
      if errors:
        raise serializers.ValidationError(errors)
      return {
        "method": method, "account_holder_name": name,
        "ifsc": ifsc, "account_number": number,
      }

    vpa = (attrs.get("vpa") or "").strip()
    if not (3 <= len(vpa) <= 100 and vpa.count("@") == 1 and VPA_REGEX.match(vpa)):
      raise serializers.ValidationError({"vpa": ["Enter a valid UPI ID, e.g. name@okhdfcbank."]})
    return {"method": method, "vpa": vpa}


class PayoutAccountSerializer(serializers.ModelSerializer):
  class Meta:
    model = SupplierPayoutAccount
    fields = [
      "method", "account_holder_name", "bank_name", "ifsc", "account_last4",
      "vpa", "updated_at",
    ]
    read_only_fields = fields
