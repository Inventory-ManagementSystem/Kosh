from django.db import models

# Create your models here.

import uuid
from django.db import models
from django.conf import settings
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator


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

class RFQ(models.Model):
  class Status(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    AWARDED = "awarded", "Awarded"
    CANCELLED = "cancelled", "Cancelled"

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey(
    "accounts.Business", on_delete=models.CASCADE, related_name="rfqs"
  )
  number = models.CharField(max_length=20)
  reorder_suggestion = models.OneToOneField(
    ReorderSuggestion, on_delete=models.SET_NULL, null=True, blank=True,
    related_name="rfq",
  )
  status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
  include_platform_pool = models.BooleanField(default=False)
  deadline = models.DateTimeField()
  notes = models.TextField(blank=True, default="")
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    related_name="+",
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["-created_at"]
    indexes = [models.Index(fields=["business", "status"])]
    constraints = [
      models.UniqueConstraint(
        fields=["business", "number"], name="uniq_rfq_number_per_business"
      ),
    ]

  def __str__(self):
    return self.number


class RFQItem(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="items")
  product = models.ForeignKey(
    "inventory.Product", on_delete=models.PROTECT, related_name="rfq_items"
  )
  product_name = models.CharField(max_length=255)
  sku = models.CharField(max_length=64)
  quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

  class Meta:
    constraints = [
      models.UniqueConstraint(
        fields=["rfq", "product"], name="uniq_product_per_rfq"
      ),
    ]

  def __str__(self):
    return f"{self.product_name} x {self.quantity}"


class RFQRecipient(models.Model):
  class Source(models.TextChoices):
    OWN = "own", "Owner's supplier"
    PLATFORM = "platform", "Platform pool"

  class Status(models.TextChoices):
    SENT = "sent", "Sent"
    VIEWED = "viewed", "Viewed"
    QUOTED = "quoted", "Quoted"
    DECLINED = "declined", "Declined"

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="recipients")
  supplier_profile = models.ForeignKey(
    "suppliers.SupplierProfile", on_delete=models.PROTECT, related_name="rfq_invitations"
  )
  supplier = models.ForeignKey(
    "suppliers.Supplier", on_delete=models.SET_NULL, null=True, blank=True,
    related_name="rfq_invitations",
  )
  source = models.CharField(max_length=10, choices=Source.choices)
  status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
  viewed_at = models.DateTimeField(null=True, blank=True)
  responded_at = models.DateTimeField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ["created_at"]
    indexes = [models.Index(fields=["supplier_profile", "status"])]
    constraints = [
      models.UniqueConstraint(
        fields=["rfq", "supplier_profile"], name="uniq_supplier_per_rfq"
      ),
    ]

  def __str__(self):
    return f"{self.rfq.number} -> {self.supplier_profile.company_name}"


MONEY = {"max_digits": 12, "decimal_places": 2}


class Quotation(models.Model):
  class Status(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    WITHDRAWN = "withdrawn", "Withdrawn"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"  

  DECIDED = (Status.ACCEPTED, Status.REJECTED)

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="quotations")
  recipient = models.OneToOneField(
    RFQRecipient, on_delete=models.CASCADE, related_name="quotation"
  )
  supplier_profile = models.ForeignKey(
    "suppliers.SupplierProfile", on_delete=models.PROTECT, related_name="quotations"
  )
  status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED)

  delivery_date = models.DateField()
  advance_amount = models.DecimalField(
    **MONEY, default=0, validators=[MinValueValidator(0)]
  )
  valid_until = models.DateField() 
  notes = models.TextField(blank=True, default="")

  subtotal = models.DecimalField(**MONEY, default=0)
  tax_total = models.DecimalField(**MONEY, default=0)
  grand_total = models.DecimalField(**MONEY, default=0)

  revision = models.PositiveIntegerField(default=1)
  submitted_at = models.DateTimeField()
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ["grand_total", "submitted_at"]
    constraints = [
      models.CheckConstraint(
        condition=models.Q(advance_amount__gte=0)
        & models.Q(advance_amount__lte=models.F("grand_total")),
        name="quotation_advance_within_total",
      ),
    ]
    indexes = [
      models.Index(fields=["rfq", "status"]),
      models.Index(fields=["supplier_profile", "status"]),
    ]

  def __str__(self):
    return f"{self.rfq.number} / {self.supplier_profile.company_name}"


class QuotationItem(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="items")
  rfq_item = models.ForeignKey(RFQItem, on_delete=models.CASCADE, related_name="quoted_items")
  quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
  unit_price = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
  gst_rate = models.DecimalField(
    max_digits=5, decimal_places=2, default=0,
    validators=[MinValueValidator(0), MaxValueValidator(40)],
  )
  line_subtotal = models.DecimalField(**MONEY)
  line_tax = models.DecimalField(**MONEY)
  line_total = models.DecimalField(**MONEY)

  class Meta:
    constraints = [
      models.UniqueConstraint(
        fields=["quotation", "rfq_item"], name="uniq_rfq_item_per_quotation"
      ),
    ]

  def __str__(self):
    return f"{self.rfq_item.product_name} x {self.quantity} @ {self.unit_price}"
