from django.contrib import admin

from .models import Customer

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
  list_display = ("name", "business", "email", "phone", "is_active", "created_at")
  list_filter = ("is_active", "business")
  search_fields = ("name", "email", "phone")
  readonly_fields = ("id", "created_at", "updated_at")
