from django.conf import settings
from django.db import models


class Notification(models.Model):
  class Kind(models.TextChoices):
    GENERAL = "general", "General"
    LOW_STOCK = "low_stock", "Low stock"
    RFQ = "rfq", "RFQ"
    QUOTATION = "quotation", "Quotation"
    PURCHASE_ORDER = "purchase_order", "Purchase order"
    PAYMENT = "payment", "Payment"
    DISCREPANCY = "discrepancy", "Discrepancy"

  user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name="notifications",
  )
  kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.GENERAL)
  title = models.CharField(max_length=150)
  body = models.TextField(blank=True, default="")
  is_read = models.BooleanField(default=False)
  read_at = models.DateTimeField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ["-created_at"]
    indexes = [
      models.Index(fields=["user", "is_read", "created_at"]),
    ]

  def __str__(self):
    return f"{self.user} - {self.title}"


class DeviceToken(models.Model):
  user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name="device_tokens",
  )
  token = models.CharField(max_length=512, unique=True)
  user_agent = models.CharField(max_length=255, blank=True, default="")
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f"{self.user} - {self.user_agent[:40] or 'device'}"
