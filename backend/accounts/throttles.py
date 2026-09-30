from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"
    rate = "5/min"

class RegisterRateThrottle(AnonRateThrottle):
    scope = "register"
    rate = "3/min"

class OTPRateThrottle(AnonRateThrottle):
    scope="otp_send"
    rate = "10/hour"

class ForgotPasswordRateThrottle(AnonRateThrottle):
    scope = "forgot_password"
    rate = "10/hour"

class VerifyOTPThrottle(AnonRateThrottle):
    scope = "otp_verify"
    rate = "5/min"

class OAuthRateThrottle(AnonRateThrottle):
    scope = "oauth"
    rate = "10/min"

class BusinessRegistrationThrottle(UserRateThrottle):
    scope = "business_register"
    rate = "5/hour"

class TokenRefreshRateThrottle(UserRateThrottle):
    scope = "token_refresh"
    rate = "10/min"
