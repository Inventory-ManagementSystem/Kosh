from django.contrib import admin

# Register your models here.
from .models import OwnerRefund, Payout, ProcurementSettings, Quotation, QuotationItem, SupplierDebt

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
@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
  list_display = ["purchase_order", "kind", "supplier_profile", "gross_amount", "deducted_amount", "amount", "status", "utr", "created_at"]
  list_filter = ["kind", "status", "mode"]
  search_fields = ["purchase_order__number", "supplier_profile__company_name", "razorpay_payout_id", "utr"]
  readonly_fields = [f.name for f in Payout._meta.fields]

  def has_add_permission(self, request):
    return False


@admin.register(SupplierDebt)
class SupplierDebtAdmin(admin.ModelAdmin):
  list_display = ["purchase_order", "supplier_profile", "amount", "recovered_amount", "status", "created_at"]
  list_filter = ["status"]
  search_fields = ["purchase_order__number", "supplier_profile__company_name"]
  readonly_fields = [f.name for f in SupplierDebt._meta.fields]

  def has_add_permission(self, request):
    return False


@admin.register(OwnerRefund)
class OwnerRefundAdmin(admin.ModelAdmin):
  list_display = ["invoice", "amount", "source", "status", "razorpay_refund_id", "created_at"]
  list_filter = ["source", "status"]
  search_fields = ["invoice__number", "razorpay_refund_id"]
  readonly_fields = [f.name for f in OwnerRefund._meta.fields]

  def has_add_permission(self, request):
    return False

