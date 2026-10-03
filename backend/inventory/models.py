from django.db import models
import uuid
from django.core.validators import MinValueValidator
from django.db.models.functions import Lower

# Create your models here.

class Category(models.Model):
  id = models.UUIDField(
    primary_key=True,
    default=uuid.uuid4,
    editable=False
  )
  business = models.ForeignKey(
    "accounts.Business",
    on_delete=models.CASCADE,
    related_name="categories"
  )

  name = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["name"]
    constraints = [
      models.UniqueConstraint(
        Lower("name"),
        "business",
        name="uniq_category_name_per_business"
      ),
    ]

  def __str__(self):
    return self.name


class Product(models.Model):
  id = models.UUIDField(
    primary_key=True,
    default=uuid.uuid4,
    editable=False
  )

  business = models.ForeignKey(
    "accounts.Business",
    on_delete=models.CASCADE,
    related_name="products"
  )

  category = models.ForeignKey(
    Category,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="products"
  )

  name = models.CharField(max_length=255)
  sku = models.CharField(max_length=64)
  description = models.TextField(blank=True)
  price = models.DecimalField(
    max_digits=12,
    decimal_places=2,
    validators=[MinValueValidator(0)]
  )
  cost_price = models.DecimalField(
    max_digits=12,
    decimal_places=2,
    null=True,
    blank=True,
    validators=[MinValueValidator(0)]
  )
  quantity = models.PositiveIntegerField(default=0)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  class Meta:
    ordering = ["-created_at"]
    constraints = [
      models.UniqueConstraint(
        fields=["business", "sku"],
        name="uniq_sku_per_business"
      ),
    ]

  def __str__(self):
    return f"{self.name} ({self.sku})"