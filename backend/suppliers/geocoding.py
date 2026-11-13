import logging
from decimal import Decimal
import requests
from django.conf import settings

logger = logging.getLogger(__name__)
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
COORD_PLACES = Decimal("0.000001")

def _lookup(address, components):
  try:
    resp = requests.get(
      GEOCODE_URL,
      params={
        "address": address,
        "components": components,
        "region": "in",
        "key": settings.GOOGLE_MAPS_SERVER_KEY,
      },
      timeout=5,
    )
    data = resp.json()
  except (requests.RequestException, ValueError):
    logger.exception("Geocoding request failed")
    return "ERROR", None

  status = data.get("status")
  if status != "OK" or not data.get("results"):
    return status, data.get("error_message", "")

  location = data["results"][0]["geometry"]["location"]
  return status, (
    Decimal(str(location["lat"])).quantize(COORD_PLACES),
    Decimal(str(location["lng"])).quantize(COORD_PLACES),
  )


def geocode(address, pincode=None):
  if not settings.GOOGLE_MAPS_SERVER_KEY or not address:
    return None

  status, result = _lookup(address, f"country:IN|postal_code:{pincode}" if pincode else "country:IN")
  if status == "ZERO_RESULTS" and pincode:
    status, result = _lookup(address, "country:IN")

  if status != "OK":
    logger.warning("Geocoding returned %s for %s %s", status, address, result or "")
    return None
  return result

def supplier_address(profile):
  return ", ".join(part for part in (profile.address, profile.city, profile.pincode) if part)


def geocode_supplier(profile):
  point = geocode(supplier_address(profile), profile.pincode)
  if point is None:
    return False
  profile.latitude, profile.longitude = point
  profile.save(update_fields=["latitude", "longitude"])
  return True

def geocode_warehouse(warehouse):
  city = warehouse.business.city
  point = geocode(", ".join(part for part in (warehouse.address, city) if part))
  if point is None:
    return False
  warehouse.latitude, warehouse.longitude = point
  warehouse.save(update_fields=["latitude", "longitude"])
  return True
