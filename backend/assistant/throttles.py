from rest_framework.throttling import UserRateThrottle

class AssistantBurstThrottle(UserRateThrottle):
  scope = "assistant"
  rate = "5/min"

class AssistantDailyThrottle(UserRateThrottle):
  scope = "assistant_daily"
  rate = "200/day"