from django.db import models

# Create your models here.

import uuid
from django.db import models


class ReorderSuggestion(models.Model):
  class Status(models.TextChoices):
    OPEN = "open", "Open"
    RFQ_CREATED = "rfq_created", "RFQ created"
    CLOSED = "closed", "Closed"
  ACTIVE = (Status.OPEN, Status.RFQ_CREATED)

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey(
    "accounts.Business", on_delete=models.CASCADE, related_name="reorder_suggestions"
  )
  product = models.ForeignKey(
    "inventory.Product", on_delete=models.CASCADE, related_name="reorder_suggestions"
  )
  status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
  method = models.CharField(max_length=10)
  stock_at_creation = models.PositiveIntegerField()
  reorder_point = models.PositiveIntegerField()
  avg_daily_dispatch = models.FloatField(default=0)
  suggested_quantity = models.PositiveIntegerField()
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["-created_at"]
    indexes = [models.Index(fields=["business", "status"])]
    constraints = [
      models.UniqueConstraint(
        fields=["product"],
        condition=models.Q(status__in=["open", "rfq_created"]),
        name="uniq_active_reorder_per_product",
      ),
    ]
