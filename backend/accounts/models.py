from django.db import models
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