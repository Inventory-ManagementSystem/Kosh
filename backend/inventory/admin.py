from django.contrib import admin

# Register your models here.

from .models import Category, Product, Warehouse

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "created_at", "updated_at")
    search_fields = ("name",)
    list_filter = ("business",)
    ordering = ("name",)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "warehouse",
        "price",
        "quantity",
        "business",
        "created_at",
    )
    search_fields = ("name", "sku")
    list_filter = ("category", "warehouse", "business")
    ordering = ("-created_at",)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "business",
        "created_at",
        "updated_at",
    )
    search_fields = ("name",)
    list_filter = ("business",)
    ordering = ("name",)
