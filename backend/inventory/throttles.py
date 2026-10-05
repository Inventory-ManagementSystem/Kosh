from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class InventoryThrottle(UserRateThrottle):
  scope = "inventory"
  rate = "60/min"
  def allow_request(self, request, view):
    if request.method in SAFE_METHODS:
      return True

    return super().allow_request(request, view)