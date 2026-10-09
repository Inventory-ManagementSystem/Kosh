from django.contrib import admin, messages

# Register your models here.

from django.utils import timezone
from .models import SupplierProfile, SupplyCategory


@admin.register(SupplyCategory)
class SupplyCategoryAdmin(admin.ModelAdmin):
  list_display = ("name", "is_active")
  list_filter = ("is_active",)
  search_fields = ("name",)


@admin.register(SupplierProfile)
class SupplierProfileAdmin(admin.ModelAdmin):
  list_display = (
    "company_name", "user", "city", "pincode", "gstin", "is_verified", "created_at",
  )
  list_filter = ("is_verified", "city", "categories")
  search_fields = ("company_name", "user__email", "gstin", "city", "pincode")
  filter_horizontal = ("categories",)
  readonly_fields = ("verified_at", "created_at", "updated_at")
  list_select_related = ("user",)
  actions = ["mark_verified", "mark_unverified"]

  @admin.action(description="Verify selected suppliers")
  def mark_verified(self, request, queryset):
    count = queryset.filter(is_verified=False).update(
      is_verified=True, verified_at=timezone.now(),
    )
    self.message_user(request, f"{count} supplier(s) verified.", messages.SUCCESS)

  @admin.action(description="Remove verification from selected suppliers")
  def mark_unverified(self, request, queryset):
    count = queryset.filter(is_verified=True).update(
      is_verified=False, verified_at=None,
    )
    self.message_user(request, f"{count} supplier(s) unverified.", messages.WARNING)

  def save_model(self, request, obj, form, change):
    if "is_verified" in form.changed_data:
      obj.verified_at = timezone.now() if obj.is_verified else None
    super().save_model(request, obj, form, change)
