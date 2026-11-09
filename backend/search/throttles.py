from rest_framework.throttling import UserRateThrottle


class SearchThrottle(UserRateThrottle):
  scope = "search"
  rate = "60/min"
