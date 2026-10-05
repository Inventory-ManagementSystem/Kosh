from rest_framework import serializers
from .models import Customer


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
    value = value.strip()
    if not value:
      raise serializers.ValidationError("Name cannot be blank.")
    return value

  def validate_email(self, value):
    return value.strip().lower()

  def validate_phone(self, value):
    value = value.strip()
    if value and not value.replace("+", "").replace(" ", "").replace("-", "").isdigit():
      raise serializers.ValidationError("Enter a valid phone number.")
    return value
