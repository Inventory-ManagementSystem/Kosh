from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
  rate = "5/min"

class RegisterRateThrottle(AnonRateThrottle):
  rate = "3/min"

class OTPRateThrottle(AnonRateThrottle):
  rate = "2/5min"

class ForgotPasswordRateThrottle(AnonRateThrottle):
  rate = "5/10min"

class VerifyOTPThrottle(AnonRateThrottle):
  rate = "5/5min"

class OAuthRateThrottle(AnonRateThrottle):
  rate = "10/min"

class BusinessRegistrationThrottle(UserRateThrottle):
  rate = "5/hour"

class TokenRefreshRateThrottle(UserRateThrottle):
  rate = "10/min"