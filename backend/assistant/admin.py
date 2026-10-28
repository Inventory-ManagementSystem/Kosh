from django.contrib import admin

# Register your models here.

from .models import ChatConversation, ChatMessage


class ChatMessageInline(admin.TabularInline):
  model = ChatMessage
  extra = 0
  fields = ["role", "content", "attachment_name", "tools_used", "created_at"]
  readonly_fields = fields
  can_delete = False


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
  list_display = ["title", "business", "user", "updated_at"]
  list_filter = ["business"]
  search_fields = ["title", "user__email"]
  readonly_fields = ["business", "user", "created_at", "updated_at"]
  inlines = [ChatMessageInline]