from django.db import models
import uuid
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError

from django.conf import settings
from django.utils import timezone

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

class Warehouse(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.OneToOneField(
    "accounts.Business",
    on_delete=models.CASCADE,
    related_name="warehouse"
  )
  name = models.CharField(max_length=100, default="Main Warehouse")
  address = models.TextField(blank=True, default="")
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return self.name


MAX_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]

def validate_image_size(image):
  if image.size > MAX_IMAGE_SIZE:
    raise ValidationError("Image size must not exceed 5 MB.")

def validate_image_content(image):
  try:
    from PIL import Image
    Image.open(image).verify()
  except Exception:
    raise ValidationError(
      "Invalid image file. Please upload a valid image."
    )


class Product(models.Model):

  OUT_OF_STOCK = "Out of Stock"
  LOW_STOCK = "Low Stock"
  IN_STOCK = "In Stock"

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
  image = models.ImageField(
    upload_to="products/",
    null=True,
    blank=True,
    validators=[
      validate_image_size,
      validate_image_content,
      FileExtensionValidator(
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS
      ),
    ],
  )
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
  warehouse = models.ForeignKey(
    Warehouse,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="products"
  )
  low_stock_threshold = models.PositiveIntegerField(default=10)

  @property
  def status(self):
    if self.quantity == 0:
      return self.OUT_OF_STOCK
    if self.quantity <= self.low_stock_threshold:
      return self.LOW_STOCK
    return self.IN_STOCK
  
  class Meta:
    ordering = ["-created_at"]
    indexes = [
      models.Index(fields=["business", "name"]),
      models.Index(fields=["business", "warehouse"]),
      models.Index(fields=["business", "category"]),
    ]
    constraints = [
      models.UniqueConstraint(
        fields=["business", "sku"],
        name="uniq_sku_per_business"
      ),
      models.CheckConstraint(
      condition=models.Q(price__gte=0),
      name="product_price_gte_0"
    ),
    models.CheckConstraint(
      condition=(
          models.Q(cost_price__isnull=True)| models.Q(cost_price__gte=0)
      ),
      name="product_cost_price_gte_0",
    ),
  ]

  def __str__(self):
    return f"{self.name} ({self.sku})"

class Outlet(models.Model):

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey(
    "accounts.Business", on_delete=models.CASCADE, related_name="outlets"
  )
  name = models.CharField(max_length=100)
  address = models.TextField(blank=True, default="")
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["name"]
    constraints = [
      models.UniqueConstraint(
        Lower("name"), "business", name="uniq_outlet_name_per_business"
      ),
    ]

  def __str__(self):
    return self.name


class DispatchNote(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey(
    "accounts.Business", on_delete=models.CASCADE, related_name="dispatch_notes"
  )
  outlet = models.ForeignKey(
    Outlet, on_delete=models.PROTECT, related_name="dispatches"
  )
  number = models.CharField(max_length=20)  # DN-0001, per business
  dispatch_date = models.DateField(default=timezone.localdate)
  notes = models.TextField(blank=True, default="")
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    related_name="+",
  )
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ["-dispatch_date", "-created_at"]
    constraints = [
      models.UniqueConstraint(
        fields=["business", "number"], name="uniq_dispatch_number_per_business"
      ),
    ]
    indexes = [models.Index(fields=["business", "dispatch_date"])]

  def __str__(self):
    return self.number


class DispatchItem(models.Model):
  dispatch_note = models.ForeignKey(
    DispatchNote, on_delete=models.CASCADE, related_name="items"
  )
  product = models.ForeignKey(
    Product, on_delete=models.PROTECT, related_name="dispatch_items"
  )
  quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

  class Meta:
    constraints = [
      models.UniqueConstraint(
        fields=["dispatch_note", "product"], name="uniq_product_per_dispatch"
      ),
    ]


class StockMovement(models.Model):

  class Reason(models.TextChoices):
    OPENING_BALANCE = "opening_balance", "Opening balance"
    GRN_RECEIVED = "grn_received", "GRN received"
    DISPATCH = "dispatch", "Dispatch"
    DAMAGED = "damaged", "Damaged"
    ADJUSTMENT = "adjustment", "Adjustment"

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey(
    "accounts.Business", on_delete=models.CASCADE, related_name="stock_movements"
  )
  product = models.ForeignKey(
    Product, on_delete=models.CASCADE, related_name="movements"
  )
  quantity_change = models.IntegerField()  # signed: + in, - out
  balance_after = models.PositiveIntegerField()
  reason = models.CharField(max_length=20, choices=Reason.choices)
  dispatch_note = models.ForeignKey(
    DispatchNote, on_delete=models.SET_NULL, null=True, blank=True,
    related_name="movements",
  )
  note = models.CharField(max_length=255, blank=True, default="")
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    related_name="+",
  )
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ["-created_at"]
    indexes = [
      models.Index(fields=["business", "product", "created_at"]),
      models.Index(fields=["business", "reason", "created_at"]),
    ]
    constraints = [
      models.CheckConstraint(
        condition=~models.Q(quantity_change=0), name="movement_change_not_zero"
      ),
    ]
