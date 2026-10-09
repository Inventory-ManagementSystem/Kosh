import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower


PINCODE_VALIDATOR = RegexValidator(
    r"^[1-9][0-9]{5}$",
    "Enter a valid 6-digit pincode.",
)


class SupplyCategory(models.Model):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "supply categories"
        constraints = [
            models.UniqueConstraint(Lower("name"), name="uniq_supply_category_name"),
        ]

    def __str__(self):
        return self.name


class SupplierProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supplier_profile",
    )
    company_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=16)
    gstin = models.CharField(max_length=15, unique=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100)
    pincode = models.CharField(max_length=6, validators=[PINCODE_VALIDATOR])
    categories = models.ManyToManyField(SupplyCategory, related_name="suppliers")

    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company_name"]
        indexes = [
            models.Index(fields=["is_verified", "city"]),
            models.Index(fields=["is_verified", "pincode"]),
        ]

    def __str__(self):
        return self.company_name