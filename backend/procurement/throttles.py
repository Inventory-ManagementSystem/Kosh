from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class QuotationWriteThrottle(UserRateThrottle):
  scope = "quotation_write"
  rate = "10/min"

  def allow_request(self, request, view):
    if request.method in SAFE_METHODS:
      return True
    return super().allow_request(request, view)
