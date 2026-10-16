from django.contrib import admin

# Register your models here.
from .models import Quotation, QuotationItem

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
