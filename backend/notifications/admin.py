from django.contrib import admin

# Register your models here.

from .models import Notification, DeviceToken


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
  list_display = ("title","user","kind","is_read","created_at")
  list_filter = ("kind", "is_read")
  search_fields = ("title","body", "user__email")
  readonly_fields = ("read_at","created_at")
  list_select_related = ("user",)


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
  list_display = ("user", "user_agent", "created_at", "updated_at")
  search_fields = ("user__email", "user_agent")
  readonly_fields = ("token", "user_agent", "created_at", "updated_at")
  list_select_related = ("user",)
