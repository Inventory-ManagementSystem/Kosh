from django.contrib import admin

from .models import Business, Profile, Employee, EmployeeInvite

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
  list_display = ("business_name", "owner", "business_type", "city", "created_at")
  list_filter = ("business_type", "city")
  search_fields = ("business_name", "owner__email", "city")
  readonly_fields = ("created_at", "updated_at")
  list_select_related = ("owner",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
  list_display = ("user", "name", "token_version")
  search_fields = ("name", "user__email", "user__username")
  readonly_fields = ("token_version",)
  list_select_related = ("user",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
  list_display = ("user", "business", "role", "phone", "is_active", "created_at")
  list_filter = ("is_active", "role", "business")
  search_fields = ("user__email", "phone", "business__business_name")
  readonly_fields = ("created_at",)
  list_select_related = ("user", "business")


@admin.register(EmployeeInvite)
class EmployeeInviteAdmin(admin.ModelAdmin):
  list_display = ("email", "business", "status", "phone", "created_at")
  list_filter = ("status", "business")
  search_fields = ("email", "phone", "business__business_name")
  readonly_fields = ("created_at",)
  list_select_related = ("business",)
