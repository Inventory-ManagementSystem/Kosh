from django.db import models
from django.db.models import Q
from django.conf import settings
# Create your models here.


class Business(models.Model):
  owner = models.OneToOneField(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name="business"
  )
  business_name = models.CharField(max_length=255)
  business_type = models.CharField(max_length=100)
  city = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  def __str__(self):
    return self.business_name
from django.contrib.auth.models import User

class Profile(models.Model):
    user=models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    name = models.CharField(max_length=50,null=True,blank=True)
    token_version=models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.user.username

class Employee(models.Model):
    ROLE_CHOICES = [("employee", "Employee")]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="employment"
    )
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="employees"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    phone = models.CharField(max_length=16, blank=True)

    def __str__(self):
        return f"{self.user.email} @ {self.business.business_name}"


class EmployeeInvite(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="invites"
    )
    email = models.EmailField()  # always stored lowercase
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    phone = models.CharField(max_length=16, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "email"],
                condition=Q(status="pending"),
                name="unique_pending_invite_per_business_email",
            )
        ]
