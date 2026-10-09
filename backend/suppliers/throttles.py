from rest_framework.throttling import UserRateThrottle

class SupplierRegistrationThrottle(UserRateThrottle):
  scope = "supplier_register"
  rate = "5/hour"
