from django.db import models

# Create your models here.
import uuid

from django.conf import settings
from django.db import models

from config.storage import PrivateMediaStorage


def chat_attachment_path(instance, filename):
  extension = filename.rsplit(".", 1)[-1].lower()
  return f"{instance.conversation.business_id}/{uuid.uuid4().hex}.{extension}"


class ChatConversation(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey(
    "accounts.Business", on_delete=models.CASCADE, related_name="chat_conversations"
  )
  user = models.ForeignKey(
    settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_conversations"
  )
  title = models.CharField(max_length=120, blank=True, default="")
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["-updated_at"]
    indexes = [
      models.Index(fields=["business", "user", "-updated_at"], name="assistant_conv_biz_user_upd"),
    ]

  def __str__(self):
    return self.title or str(self.id)


class ChatMessage(models.Model):
  class Role(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  conversation = models.ForeignKey(
    ChatConversation, on_delete=models.CASCADE, related_name="messages"
  )
  role = models.CharField(max_length=10, choices=Role.choices)
  content = models.TextField()
  tools_used = models.JSONField(default=list, blank=True)
  attachment = models.FileField(
    upload_to=chat_attachment_path, storage=PrivateMediaStorage, null=True, blank=True
  )
  attachment_name = models.CharField(max_length=255, blank=True, default="")
  attachment_type = models.CharField(max_length=50, blank=True, default="")
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ["created_at", "-role"]
    indexes = [
      models.Index(fields=["conversation", "created_at"], name="assistant_msg_conv_created"),
    ]

  def __str__(self):
    return f"{self.role}: {self.content[:40]}"