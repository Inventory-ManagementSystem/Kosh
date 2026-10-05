from django.db import models

# Create your models here.

from django.db import models
import uuid


class Customer(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey(
    "accounts.Business",
    on_delete=models.CASCADE,
    related_name="customers"
  )

  name = models.CharField(max_length=255)
  email = models.EmailField(blank=True)
  phone = models.CharField(max_length=16, blank=True)
  address = models.TextField(blank=True)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["name"]
    indexes = [
      models.Index(fields=["business", "name"]),
    ]

  def __str__(self):
    return self.name
