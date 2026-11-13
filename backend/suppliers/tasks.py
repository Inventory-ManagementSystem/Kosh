from celery import shared_task
from .geocoding import geocode_supplier
from .models import SupplierProfile


@shared_task
def geocode_supplier_profile(profile_id):
  profile = SupplierProfile.objects.filter(pk=profile_id).first()
  if profile is None:
    return False
  return geocode_supplier(profile)