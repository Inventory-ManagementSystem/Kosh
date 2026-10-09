from rest_framework import serializers
from .models import Customer
import re
from accounts.validators import validate_phone_number


class CustomerSerializer(serializers.ModelSerializer):
  class Meta:
    model = Customer
    fields = [
      "id",
      "name",
      "email",
      "phone",
      "address",
      "is_active",
      "created_at",
      "updated_at",
    ]
    read_only_fields = ["id", "created_at", "updated_at"]

  def validate_name(self, value):
    value = " ".join(value.split())
    if not value:
      raise serializers.ValidationError("Name cannot be blank.")
    return value

  def validate_email(self, value):
    return value.strip().lower()

  def validate_phone(self, value):
    cleaned = re.sub(r"[\s-]", "", value)
    return validate_phone_number(cleaned)

  def validate(self, attrs):
    others = Customer.objects.filter(business=self.context["business"])
    if self.instance is not None:
      others = others.exclude(pk=self.instance.pk)

    for field, label in (("phone", "phone number"), ("email", "email")):
      value = attrs.get(field)
      if not value:
        continue
      existing = others.filter(**{field: value}).first()
      if existing:
        if existing.is_active:
          message = f"A customer with this {label} already exists."
        else:
          message = (
            f"A deactivated customer with this {label} already exists. "
            "Reactivate that customer instead."
          )
        raise serializers.ValidationError({field: message})
    return attrs
