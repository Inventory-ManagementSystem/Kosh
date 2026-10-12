from rest_framework.throttling import UserRateThrottle
from rest_framework.permissions import SAFE_METHODS

class SupplierRegistrationThrottle(UserRateThrottle):
  scope = "supplier_register"
  rate = "5/hour"

class OwnerSupplierThrottle(UserRateThrottle):
  scope = "owner_supplier"
  rate = "60/min"

  def allow_request(self, request, view):
    if request.method in SAFE_METHODS:
      return True
    return super().allow_request(request, view)
