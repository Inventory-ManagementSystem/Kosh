from django.contrib import admin

# Register your models here.
from .models import Quotation, QuotationItem, ProcurementSettings

class QuotationItemInline(admin.TabularInline):
  model = QuotationItem
  extra = 0
  can_delete = False
  readonly_fields = [
    "rfq_item", "quantity", "unit_price", "gst_rate",
    "line_subtotal", "line_tax", "line_total",
  ]

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
  list_display = ["rfq", "supplier_profile", "status", "grand_total", "revision", "submitted_at"]
  list_filter = ["status"]
  search_fields = ["rfq__number", "supplier_profile__company_name"]
  readonly_fields = [
    "rfq", "recipient", "supplier_profile", "subtotal", "tax_total", "grand_total",
    "revision", "submitted_at", "created_at", "updated_at",
  ]
  inlines = [QuotationItemInline]

@admin.register(ProcurementSettings)
class ProcurementSettingsAdmin(admin.ModelAdmin):
  list_display = [
    "business", "auto_rfq_include_manual", "auto_rfq_include_platform_pool", "updated_at",
  ]
  list_editable = ["auto_rfq_include_manual", "auto_rfq_include_platform_pool"]
  search_fields = ["business__business_name"]
  autocomplete_fields = []
