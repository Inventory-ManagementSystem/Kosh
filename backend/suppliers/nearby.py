import math
from .models import Supplier, SupplierProfile

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEGREE = 111.0
RADIUS_CHOICES = [5, 10, 50]

def haversine_km(lat1, lng1, lat2, lng2):
  lat1, lng1, lat2, lng2 = (math.radians(float(v)) for v in (lat1, lng1, lat2, lng2))
  a = (
    math.sin((lat2 - lat1) / 2) ** 2
    + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
  )
  return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat, lng, radius_km):
  lat, lng = float(lat), float(lng)
  dlat = radius_km / KM_PER_DEGREE
  dlng = radius_km / (KM_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
  return (round(lat - dlat, 6), round(lat + dlat, 6)), (round(lng - dlng, 6), round(lng + dlng, 6))

def business_origin(business):
  from inventory.services import get_warehouse
  from .geocoding import geocode_warehouse

  warehouse = get_warehouse(business)
  if warehouse.latitude is None and not geocode_warehouse(warehouse):
    return None, warehouse
  return (warehouse.latitude, warehouse.longitude), warehouse


def suppliers_within(business, origin, radius_km, category=None, source="all"):
  lat_range, lng_range = bounding_box(*origin, radius_km)
  profiles = (
    SupplierProfile.objects.filter(
      is_verified=True,
      latitude__range=lat_range,
      longitude__range=lng_range,
    )
    .select_related("user")
    .prefetch_related("categories")
  )
  if category is not None:
    profiles = profiles.filter(categories=category)

  linked = {
    record.linked_account_id: record
    for record in Supplier.objects.filter(
      business=business, is_active=True, linked_account__isnull=False
    )
  }
  if source == "mine":
    profiles = profiles.filter(pk__in=list(linked))
  elif source == "platform":
    profiles = profiles.exclude(pk__in=list(linked))
  nearby = []
  for profile in profiles:
    distance = haversine_km(origin[0], origin[1], profile.latitude, profile.longitude)
    if distance <= radius_km:
      profile.distance_km = round(distance, 2)
      profile.supplier_record = linked.get(profile.pk)
      nearby.append(profile)
  nearby.sort(key=lambda p: p.distance_km)
  return nearby
