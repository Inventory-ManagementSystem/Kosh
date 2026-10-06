from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Business, Profile, Employee, EmployeeInvite
from .utils import get_role, get_owned_business, invite_cutoff, purge_expired_invites, INVITE_TTL
from .serializers import (
  RegisterSerializer,
  LoginSerializer,
  ForgotPasswordSerializer,
  VerifyResetOTPSerializer,
  ResetPasswordSerializer,
  ChangePasswordSerializer,
  BusinessRegistrationSerializer,
  VerifyRegistrationOTPSerializer,
  ResendRegistrationOTPSerializer,
  InviteEmployeeSerializer,

)
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
import secrets
from rest_framework_simplejwt.token_blacklist.models import (
    OutstandingToken,
    BlacklistedToken,
)

from django.contrib.auth.models import User
from django.contrib.auth import logout as django_logout
from django.core.mail import send_mail
from django.core.cache import cache
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.conf import settings
import logging
logger = logging.getLogger(__name__)

from drf_spectacular.utils import (extend_schema,OpenApiResponse,OpenApiExample)
from drf_spectacular.types import OpenApiTypes


from .throttles import (
    LoginRateThrottle,
    RegisterRateThrottle,
    OTPRateThrottle,
    ForgotPasswordRateThrottle,
    VerifyOTPThrottle,
    OAuthRateThrottle,
    BusinessRegistrationThrottle,
    TokenRefreshRateThrottle,
    ChangePasswordThrottle,
    ResetPasswordThrottle,
    InviteEmployeeThrottle,
)
from rest_framework.throttling import (UserRateThrottle)
from django.shortcuts import redirect
from .responses import success_response, error_response
from .swagger import ok_example, err_example, resp, THROTTLED_EXAMPLE, UNAUTHORIZED_RESPONSE
from rest_framework.authentication import SessionAuthentication

class SessionAuthNoCSRF(SessionAuthentication):
    def enforce_csrf(self, request):
        return

REFRESH_COOKIE = "refresh_token"

def set_refresh_cookie(response, refresh_token):
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=str(refresh_token),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path="/accounts/",
    )

def delete_refresh_cookie(response):
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/accounts/",
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )

@extend_schema(
    summary="Refresh Access Token",
    description="Reads the refresh token from the HttpOnly cookie. No request body.",
    request=None,
    responses={
        200: resp("New access token issued.",
                  ok_example("Token Refreshed", "Token refreshed.",
                             data={"access": "eyJhbGciOiJIUzI1NiIs..."})),
        401: resp("Cookie missing, or token invalid or blacklisted.",
                  err_example("Missing", "No refresh token.", "REFRESH_TOKEN_MISSING"),
                  err_example("Invalid", "Invalid or expired token.", "REFRESH_TOKEN_INVALID")),
    },
)

class CookieTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [TokenRefreshRateThrottle]

    def post(self, request):
        raw_refresh = request.COOKIES.get(REFRESH_COOKIE)
        if not raw_refresh:
             return error_response(
                "No refresh token.", "REFRESH_TOKEN_MISSING",
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            token = RefreshToken(raw_refresh)  # checks signature, expiry and blacklist
            profile = Profile.objects.get(user_id=token["user_id"])
            if token.get("token_version") != profile.token_version:
                raise TokenError("Stale token")
        except (TokenError, KeyError, Profile.DoesNotExist):
            response = error_response(
                "Invalid or expired token.", "REFRESH_TOKEN_INVALID",
                status=status.HTTP_401_UNAUTHORIZED,
            )
            delete_refresh_cookie(response)
            return response

        serializer = TokenRefreshSerializer(data={"refresh": raw_refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken):
            response = error_response(
                "Invalid or expired token.", "REFRESH_TOKEN_INVALID",
                status=status.HTTP_401_UNAUTHORIZED,
            )
            delete_refresh_cookie(response)
            return response

        data = serializer.validated_data
        response = success_response(
            "Token refreshed.", data={"access": data["access"]}
        )
        if "refresh" in data:
            set_refresh_cookie(response, data["refresh"])
        return response

@extend_schema(
    summary="Register User",
    description=(
        "Validates the registration details and sends a 6-digit OTP "
        "to the provided email address. The user account is created "
        "only after the OTP is successfully verified."
    ),
    request=RegisterSerializer,
    examples=[
        OpenApiExample(
            "Valid Registration",
            summary="Request registration OTP",
            description="Use this data to request an email verification OTP.",
            value={
                "name": "John Doe",
                "email": "john@example.com",
                "password": "John@1234"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Duplicate Email",
            summary="Email already exists",
            description="Use an email address that is already registered.",
            value={
                "name": "John Doe",
                "email": "john@example.com",
                "password": "NewUser@1234"
            },
            request_only=True,
        ),
    ],
    responses={
        200: resp("Registration OTP sent.",
                ok_example("OTP Sent", "OTP has been sent to your email.")),
        400: resp("Validation error.",
                err_example("Duplicate Email", "Validation failed.", "VALIDATION_ERROR",
                            errors={"email": ["Email already exists"]})),
        429: resp("Resend cooldown active, or too many requests.",
                err_example("Cooldown Active", "Please wait before requesting another OTP.",
                            "OTP_COOLDOWN", details={"retry_after": 43}),
                THROTTLED_EXAMPLE),
        503: resp("Email could not be sent.",
            err_example("Email Failed", "Could not send the email. Please try again.",
                        "EMAIL_SEND_FAILED")),
    },
)
class RegisterApi(APIView):
    authentication_classes = []
    throttle_classes=[RegisterRateThrottle]
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation failed.", "VALIDATION_ERROR",
                                   errors=serializer.errors)

        email = serializer.validated_data["email"]
        name = serializer.validated_data["name"]
        password = serializer.validated_data["password"]

        cooldown_key = f"registration_resend:{email}"
        otp_key = f"registration_otp:{email}"
        data_key = f"registration_data:{email}"

        if not cache.add(cooldown_key, True, timeout=60):
            return error_response(
                "Please wait before requesting another OTP.", "OTP_COOLDOWN",
                details={"retry_after": max(cache.ttl(cooldown_key), 0)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        otp = str(secrets.randbelow(900000) + 100000)

        try:
            send_mail(
                "Kosh Email Verification OTP",
                f"Your Kosh email verification OTP is {otp}. "
                "This OTP is valid for 5 minutes.",
                None,
                [email],
            )
        except Exception:
            cache.delete(cooldown_key)
            return error_response(
                "Could not send the email. Please try again.", "EMAIL_SEND_FAILED",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        cache.delete(f"registration_attempts:{email}")
        cache.set(otp_key, otp, timeout=300)
        cache.set(
            data_key,
            {"name": name, "email": email, "password": make_password(password)},
            timeout=300,
        )

        return success_response("OTP has been sent to your email.")

@extend_schema(
    summary="Verify Registration OTP",
    description=(
        "Verifies the 6-digit OTP sent to the user's email during "
        "registration. The user account is created only after the OTP "
        "is successfully verified. A maximum of 5 incorrect attempts "
        "are allowed."
    ),
    request=VerifyRegistrationOTPSerializer,
    examples=[
        OpenApiExample(
            "Valid OTP",
            summary="Verify registration",
            description="Use the OTP received on the registered email.",
            value={
                "email": "john@example.com",
                "otp": "123456"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Invalid OTP",
            summary="Incorrect OTP",
            description="Use an incorrect OTP to test the attempt limit.",
            value={
                "email": "john@example.com",
                "otp": "654321"
            },
            request_only=True,
        ),
    ],
    responses={
        201: resp("Email verified and user registered.",
                ok_example("Registration Success", "Email verified and registration successful.")),
        400: resp("Validation error, wrong OTP or expired OTP.",
                err_example("Invalid OTP", "Invalid OTP.", "INVALID_OTP",
                            details={"remaining_attempts": 4}),
                err_example("Expired OTP", "OTP has expired. Please register again.", "OTP_EXPIRED"),
                err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"otp": ["Ensure this field has at least 6 characters."]})),
        409: resp("Email already registered.",
                err_example("Email Exists", "Email already exists.", "EMAIL_EXISTS")),
        429: resp("Too many incorrect attempts, or throttled.",
                err_example("Too Many Attempts",
                            "Too many incorrect OTP attempts. Please register again.",
                            "OTP_ATTEMPTS_EXCEEDED"),
                THROTTLED_EXAMPLE),
    },
)

class VerifyRegistrationOTPApi(APIView):
    authentication_classes = []
    throttle_classes=[VerifyOTPThrottle]
    def post(self, request):
        serializer = VerifyRegistrationOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation failed.", "VALIDATION_ERROR",
                                    errors=serializer.errors)

        email = serializer.validated_data["email"]
        submitted_otp = serializer.validated_data["otp"]

        otp_key = f"registration_otp:{email}"
        data_key = f"registration_data:{email}"
        attempts_key = f"registration_attempts:{email}"

        stored_otp = cache.get(otp_key)
        registration_data = cache.get(data_key)

        if not stored_otp or not registration_data:
            return error_response("OTP has expired. Please register again.", "OTP_EXPIRED")

        attempts = cache.get(attempts_key, 0)

        if attempts >= 5:
            cache.delete(otp_key)
            cache.delete(data_key)
            cache.delete(attempts_key)

            return error_response("Too many incorrect OTP attempts. Please register again.", "OTP_ATTEMPTS_EXCEEDED", 
                                  status=status.HTTP_429_TOO_MANY_REQUESTS)

        if not secrets.compare_digest(str(stored_otp).encode(), submitted_otp.encode()):
            attempts += 1

            cache.set(
                attempts_key,
                attempts,
                timeout=300
            )

            return error_response("Invalid OTP.", "INVALID_OTP", 
                                  details={"remaining_attempts": 5 - attempts})

        if User.objects.filter(email__iexact=email).exists():
            cache.delete(otp_key)
            cache.delete(data_key)
            cache.delete(attempts_key)
            return error_response("Email already exists.", "EMAIL_EXISTS",
                                  status=status.HTTP_409_CONFLICT)
    
        try:
            with transaction.atomic():
                user = User.objects.create(
                    username=registration_data["email"],
                    email=registration_data["email"],
                    password=registration_data["password"],
                )
                user.profile.name = registration_data["name"]
                user.profile.save(update_fields=["name"])

        except IntegrityError:
           return error_response("Email already exists.", "EMAIL_EXISTS", 
                                 status=status.HTTP_409_CONFLICT)

        cache.delete(otp_key)
        cache.delete(data_key)
        cache.delete(attempts_key)
        cache.delete(f"registration_resend:{email}")

        return success_response("Email verified and registration successful.", 
                                status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Login User",
    request=LoginSerializer,
    examples=[
        OpenApiExample(
            "Login with Email",
            summary="Successful login using email",
            value={
                "email": "john@example.com",
                "password": "John@1234"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Invalid Credentials",
            summary="Failed login",
            value={
                "email": "john@example.com",
                "password": "WrongPassword@123"
            },
            request_only=True,
        ),
    ],
    responses={
        200: resp("Login successful. The refresh token is set as an HttpOnly cookie.",
                ok_example("Login Success", "Login successful.",
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": False, "role": None})),
        400: resp("Invalid credentials or validation error.",
                err_example("Invalid Credentials", "Invalid email or password.", "INVALID_CREDENTIALS",
                            errors={"non_field_errors": ["Invalid email or password."]}),
                err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"email": ["This field is required."]})),
        429: resp("Too many login attempts.", THROTTLED_EXAMPLE),
    },
)
class LoginApi(APIView):
  authentication_classes = []
  throttle_classes=[LoginRateThrottle]
  def post(self,request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
      data=serializer.validated_data
      user= data["user"]
      has_business = Business.objects.filter(owner=user).exists()
      response = success_response(
                    "Login successful.",
                    data={"access": data["access"], 
                        "has_business": has_business,
                        "role": get_role(user)},
                )
      set_refresh_cookie(response, data["refresh"])
      return response

    if "non_field_errors" in serializer.errors:
        return error_response(
            "Invalid email or password.", "INVALID_CREDENTIALS",
            errors=serializer.errors,
        )
    return error_response(
        "Validation failed.", "VALIDATION_ERROR",
        errors=serializer.errors,
    )


@extend_schema(
    summary="Get User Profile",
    description="Retrieve the profile information of the currently authenticated user.",
    responses={
        200: resp("Profile retrieved.",
                ok_example("Profile Success", "Profile retrieved.",
                            data={"id": 1, "name": "John Doe", "email": "john@example.com", "role": None})),
        401: UNAUTHORIZED_RESPONSE,
    },
)
class ProfileApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes=[UserRateThrottle]
  def get(self,request):
    user =request.user
    return success_response("Profile retrieved.", data={
        "id": user.id,
        "name": user.profile.name,
        "email": user.email,
        "role": get_role(user),
    })



@extend_schema(
    summary="Logout User",
    description=(
        "Blacklists the refresh token from the HttpOnly cookie and clears the cookie. "
        "No access token is needed, so logout still works after the access token has "
        "expired. No request body. Returns 200 even if the cookie is missing or invalid."
    ),
    request=None,
    responses={
        200: resp("Logout successful. The refresh cookie is cleared.",
                ok_example("Logout Success", "Logout successful.")),
        429: resp("Too many requests.", THROTTLED_EXAMPLE),
    },
)

class LogoutApi(APIView):
  authentication_classes = []
  throttle_classes=[UserRateThrottle]
  def post(self, request):
    refresh_token = request.COOKIES.get(REFRESH_COOKIE)
    if refresh_token:
      try:
        RefreshToken(refresh_token).blacklist()
      except TokenError:
        pass

    response = success_response("Logout successful.")
    delete_refresh_cookie(response)
    return response


@extend_schema(
    summary="Request Password Reset",
    description="Sends a password reset OTP to the user's registered email address.",
    request=ForgotPasswordSerializer,
    examples=[
        OpenApiExample(
            "Valid Email",
            summary="Successful password reset request",
            value={
                "email": "john@example.com"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Invalid Email",
            summary="Failed password reset request",
            value={
                "email": "unknown@example.com"
            },
            request_only=True,
        ),
    ],
    responses={
        200: resp("Generic response, whether or not the email exists.",
                ok_example("OTP Sent",
                            "If an account exists with this email, a password reset OTP has been sent.")),
        400: resp("Validation error.",
                err_example("Invalid Email", "Validation failed.", "VALIDATION_ERROR",
                            errors={"email": ["Enter a valid email address."]})),
        429: resp("Resend cooldown active, or throttled.",
                err_example("OTP Cooldown", "Please wait before requesting another OTP.",
                            "OTP_COOLDOWN", details={"retry_after": 45}),
                THROTTLED_EXAMPLE),
    },
)
class ForgotPasswordApi(APIView):
    authentication_classes = []
    throttle_classes=[ForgotPasswordRateThrottle]
    def post(self, request):

        serializer = ForgotPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Validation failed.", "VALIDATION_ERROR",
                errors=serializer.errors,
            )

        email = serializer.validated_data["email"].lower()

        cooldown_key = f"password_reset_resend:{email}"

        retry_after = cache.ttl(cooldown_key)

        if retry_after > 0:
            return error_response(
                "Please wait before requesting another OTP.", "OTP_COOLDOWN",
                details={"retry_after": retry_after},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        user = User.objects.filter(email__iexact=email).first()

        cache.set(cooldown_key, True, timeout=60)

        if user:

            otp = str(secrets.randbelow(900000) + 100000)

            cache.delete(f"password_reset_attempts:{email}")

            otp_key = f"password_reset_otp:{email}"

            cache.set(
                otp_key,
                otp,
                timeout=300
            )

            try:
                send_mail(
                    "Kosh Password Reset OTP",
                    f"Your password reset OTP is {otp}. "
                    "This OTP is valid for 5 minutes.",
                    None,
                    [email],
                )
            except Exception:
                logger.exception("Password reset email failed")

        return success_response(
            "If an account exists with this email, "
            "a password reset OTP has been sent."
        )


@extend_schema(
    summary="Verify Password Reset OTP",
    description="Verifies the OTP sent to the user's email during the password reset process.",
    request=VerifyResetOTPSerializer,
    examples=[
        OpenApiExample(
            "Valid OTP",
            summary="Successful OTP verification",
            value={
                "email": "john@example.com",
                "otp": "123456"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Invalid OTP",
            summary="Failed OTP verification",
            value={
                "email": "john@example.com",
                "otp": "654321"
            },
            request_only=True,
        ),
    ],
    responses={
        200: resp("OTP verified. Use the reset token in the next call.",
                ok_example("OTP Verified", "OTP verified successfully.",
                            data={"reset_token": "example-reset-token"})),
        400: resp("Validation error, wrong OTP or expired OTP.",
                err_example("Invalid OTP", "Invalid OTP.", "INVALID_OTP",
                            details={"remaining_attempts": 4}),
                err_example("Expired OTP", "OTP has expired. Please request a new one.",
                            "OTP_EXPIRED"),
                err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"otp": ["Ensure this field has at least 6 characters."]})),
        429: resp("Too many incorrect attempts, or throttled.",
                err_example("Too Many Attempts",
                            "Too many incorrect attempts. Please request a new OTP.",
                            "OTP_ATTEMPTS_EXCEEDED"),
                THROTTLED_EXAMPLE),
    },
)
class VerifyResetOTPApi(APIView):
    authentication_classes = []
    throttle_classes=[VerifyOTPThrottle]
    def post(self, request):

        serializer = VerifyResetOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Validation failed.", "VALIDATION_ERROR",
                errors=serializer.errors,
            )

        email = serializer.validated_data["email"].lower()
        otp = serializer.validated_data["otp"]

        otp_key = f"password_reset_otp:{email}"
        attempts_key = f"password_reset_attempts:{email}"

        stored_otp = cache.get(otp_key)

        if stored_otp is None:
            return error_response(
            "OTP has expired. Please request a new one.", "OTP_EXPIRED",
        )

        attempts = cache.get(attempts_key, 0)

        if attempts >= 5:
            cache.delete(otp_key)
            cache.delete(attempts_key)

            return error_response(
                "Too many incorrect attempts. Please request a new OTP.",
                "OTP_ATTEMPTS_EXCEEDED",
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not secrets.compare_digest(str(stored_otp), otp):

            attempts += 1

            if attempts >= 5:
                cache.delete(otp_key)
                cache.delete(attempts_key)

                return error_response(
                    "Too many incorrect attempts. Please request a new OTP.",
                    "OTP_ATTEMPTS_EXCEEDED",
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            cache.set(
                attempts_key,
                attempts,
                timeout=300
            )

            return error_response(
                "Invalid OTP.", "INVALID_OTP",
                details={"remaining_attempts": 5 - attempts},
            )

        user = User.objects.filter(email__iexact=email).first()

        if user is None:
            return error_response("Invalid OTP.", "INVALID_OTP")

        reset_token = secrets.token_urlsafe(32)

        reset_token_key = f"password_reset_token:{reset_token}"

        cache.set(
            reset_token_key,
            user.id,
            timeout=600
        )

        cache.delete(otp_key)
        cache.delete(attempts_key)

        return success_response(
            "OTP verified successfully.",
            data={"reset_token": reset_token},
        )


@extend_schema(
    summary="Reset Password",
    description="Resets the user's password using the reset token received after OTP verification.",
    request=ResetPasswordSerializer,
    examples=[
        OpenApiExample(
            "Valid Reset Password",
            summary="Successful password reset",
            value={
                "reset_token": "example-reset-token",
                "new_password": "NewPassword@123",
                "confirm_password": "NewPassword@123"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Invalid Reset Token",
            summary="Failed password reset",
            value={
                "reset_token": "invalid-reset-token",
                "new_password": "NewPassword@123",
                "confirm_password": "NewPassword@123"
            },
            request_only=True,
        ),
    ],
    responses={
        200: resp("Password reset. All existing sessions are invalidated.",
                ok_example("Password Reset Success", "Password reset successfully.")),
        400: resp("Invalid reset token or validation error.",
                err_example("Invalid Reset Token", "Invalid or expired reset token.",
                            "INVALID_RESET_TOKEN"),
                err_example("Password Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"confirm_password": ["Passwords do not match."]})),
        429: resp("Too many requests.", THROTTLED_EXAMPLE),
    },
)
class ResetPasswordApi(APIView):
    authentication_classes = []
    throttle_classes=[ResetPasswordThrottle]

    def post(self, request):

        serializer = ResetPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Validation failed.", "VALIDATION_ERROR",
                errors=serializer.errors,
            )

        reset_token = serializer.validated_data["reset_token"]
        new_password = serializer.validated_data["new_password"]

        reset_token_key = f"password_reset_token:{reset_token}"

        user_id = cache.get(reset_token_key)

        if user_id is None:
            return error_response(
                "Invalid or expired reset token.", "INVALID_RESET_TOKEN",
            )

        user = User.objects.filter(id=user_id).first()

        if user is None:
            cache.delete(reset_token_key)

            return error_response(
                "Invalid or expired reset token.", "INVALID_RESET_TOKEN",
            )

        with transaction.atomic():
            user.set_password(new_password)
            user.save()

            user.profile.token_version += 1
            user.profile.save(update_fields=["token_version"])

            for outstanding_token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding_token)

        cache.delete(reset_token_key)

        return success_response("Password reset successfully.")


@extend_schema(
    summary="Change Password",
    description="Changes the password of the currently authenticated user.",
    request=ChangePasswordSerializer,
    examples=[
        OpenApiExample(
            "Valid Password Change",
            summary="Successful password change",
            value={
                "current_password": "OldPassword@123",
                "new_password": "NewPassword@123",
                "confirm_password": "NewPassword@123"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Incorrect Current Password",
            summary="Failed password change",
            value={
                "current_password": "WrongPassword@123",
                "new_password": "NewPassword@123",
                "confirm_password": "NewPassword@123"
            },
            request_only=True,
        ),
    ],
    responses={
        200: resp("Password changed. The refresh cookie is cleared, so the user must log in again.",
                ok_example("Password Change Success", "Password changed successfully.")),
        400: resp("Wrong current password or validation error.",
                err_example("Incorrect Current Password", "Current password is incorrect.",
                            "INVALID_CURRENT_PASSWORD"),
                err_example("Password Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"confirm_password": ["Passwords do not match."]})),
        401: UNAUTHORIZED_RESPONSE,
        429: resp("Too many requests.", THROTTLED_EXAMPLE),
    },
)
class ChangePasswordApi(APIView):

    permission_classes=[ IsAuthenticated]
    throttle_classes=[ChangePasswordThrottle]

    def post(self, request):
        serializer=ChangePasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Validation failed.", "VALIDATION_ERROR",
                errors=serializer.errors,
            )
        user=request.user

        current_password=serializer.validated_data["current_password"]
        new_password=serializer.validated_data["new_password"]

        if not user.check_password(current_password):
            return error_response(
                "Current password is incorrect.", "INVALID_CURRENT_PASSWORD",
            )
        
        with transaction.atomic():
            user.set_password(new_password)
            user.save()

            user.profile.token_version += 1
            user.profile.save(update_fields=["token_version"])

            for outstanding_token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding_token)

        response = success_response("Password changed successfully.")
        delete_refresh_cookie(response)
        return response


@extend_schema(
    summary="Generate JWT for Google User",
    description=(
        "Generates access and refresh JWT tokens for a user "
        "authenticated through Google OAuth."
    ),
    responses={
        200: resp("Login successful. The refresh token is set as an HttpOnly cookie.",
                ok_example("Google Login Without Business", "Login successful.",
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": False, "role": None}),
                ok_example("Google Login With Business", "Login successful.",
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": True, "role": "owner"})),
        401: resp("Google authentication failed.",
                err_example("Google Authentication Failed", "Google authentication failed.",
                            "GOOGLE_AUTH_FAILED")),
        429: resp("Too many requests.", THROTTLED_EXAMPLE),
    },
    tags=["Authentication"],
)
class GoogleJWTApi(APIView):
  authentication_classes = [SessionAuthNoCSRF]
  throttle_classes=[OAuthRateThrottle]
  def post(self, request):
    user = request.user
    if not user.is_authenticated:
      return error_response(
            "Google authentication failed.", "GOOGLE_AUTH_FAILED",
            status=status.HTTP_401_UNAUTHORIZED,
        )

    refresh = RefreshToken.for_user(user)
    refresh["token_version"] = user.profile.token_version
    has_business = Business.objects.filter(owner=request.user).exists()

    response = success_response(
        "Login successful.",
        data={
            "access": str(refresh.access_token),
            "has_business": has_business,
            "role": get_role(user)
        },
    )
    set_refresh_cookie(response, refresh)
    django_logout(request._request)
    return response

@extend_schema(
    summary="Generate JWT for GitHub User",
    description=(
        "Generates access and refresh JWT tokens for a user "
        "authenticated through GitHub OAuth."
    ),
    responses={
        200: resp("Login successful. The refresh token is set as an HttpOnly cookie.",
                ok_example("Github Login Without Business", "Login successful.",
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": False, "role": None}),
                ok_example("Github Login With Business", "Login successful.",
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": True, "role": "owner"})),
        401: resp("Github authentication failed.",
                err_example("Github Authentication Failed", "Github authentication failed.",
                            "GITHUB_AUTH_FAILED")),
        429: resp("Too many requests.", THROTTLED_EXAMPLE),
    },
    tags=["Authentication"],
)
class GitHubJWTApi(APIView):
    authentication_classes = [SessionAuthNoCSRF]
    throttle_classes = [OAuthRateThrottle]

    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return error_response(
                        "Github authentication failed.", "GITHUB_AUTH_FAILED",
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
        refresh = RefreshToken.for_user(user)
        refresh["token_version"] = user.profile.token_version
        has_business = Business.objects.filter(
            owner=request.user
        ).exists()

        response = success_response(
            "Login successful.",
            data={
                "access": str(refresh.access_token),
                "has_business": has_business,
                "role": get_role(user)
            },
        )
        set_refresh_cookie(response, refresh)
        django_logout(request._request)
        return response

def google_login_cancelled(request):
    return redirect(
        "https://koshh.me/oauth/callback?error=google_login_cancelled"
    )


@extend_schema(
    summary="Register Business",
    description="Creates business details for the authenticated business owner.",
    request=BusinessRegistrationSerializer,
    examples=[
        OpenApiExample(
            "Valid Business Registration",
            summary="Successful business registration",
            value={
                "business_name": "Kosh Technologies",
                "business_type": "Retail",
                "city": "Ghaziabad"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Invalid Business Registration",
            summary="Failed business registration",
            value={
                "business_name": "",
                "business_type": "Retail",
                "city": "Ghaziabad"
            },
            request_only=True,
        ),
    ],
    responses={
        201: resp("Business registered.",
                ok_example("Business Registration Success", "Business registered successfully.",
                            data={"id": 1, "business_name": "Kosh Technologies",
                                "business_type": "Retail", "city": "Ghaziabad"})),
        400: resp("Validation error.",
                err_example("Invalid Business Details", "Validation failed.", "VALIDATION_ERROR",
                            errors={"business_name": ["This field may not be blank."]})),
        401: UNAUTHORIZED_RESPONSE,
        409: resp("Business already registered for this user.",
                err_example("Business Already Registered", "Business is already registered.",
                            "BUSINESS_EXISTS"),
                err_example("Is Employee", "Employees cannot register a business.", 
                            "EMPLOYEE_CANNOT_REGISTER_BUSINESS")),
    },
)
class BusinessRegistration(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes=[BusinessRegistrationThrottle]
  def post(self, request):
    if Employee.objects.filter(user=request.user).exists():
        return error_response(
            "Employees cannot register a business.", "EMPLOYEE_CANNOT_REGISTER_BUSINESS",
            status=status.HTTP_409_CONFLICT,
        )
    if Business.objects.filter(owner=request.user).exists():
      return error_response(
            "Business is already registered.", "BUSINESS_EXISTS",
            status=status.HTTP_409_CONFLICT,
        )
    serializer = BusinessRegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            "Validation failed.", "VALIDATION_ERROR",
            errors=serializer.errors,
        )

    try:
        business = serializer.save(owner=request.user)
    except IntegrityError:
        return error_response(
            "Business is already registered.", "BUSINESS_EXISTS",
            status=status.HTTP_409_CONFLICT,
        )

    EmployeeInvite.objects.filter(email__iexact=request.user.email).delete()

    return success_response(
        "Business registered successfully.",
        data={
            "id": business.id,
            "business_name": business.business_name,
            "business_type": business.business_type,
            "city": business.city,
        },
        status=status.HTTP_201_CREATED,
    )

@extend_schema(
    summary="Resend Registration OTP",
    description=(
        "Sends a new OTP for a pending registration. Only the email is "
        "needed, because the registration data is already held server-side."
    ),
    request=ResendRegistrationOTPSerializer,
    examples=[
        OpenApiExample(
            "Resend OTP",
            summary="Resend the registration OTP",
            value={"email": "john@example.com"},
            request_only=True,
        ),
    ],
    responses={
        200: resp("OTP resent.",
                  ok_example("OTP Resent", "OTP has been resent to your email.")),
        400: resp("Validation error, or the pending registration expired.",
                  err_example("Registration Expired",
                              "Registration session expired. Please register again.",
                              "REGISTRATION_EXPIRED"),
                  err_example("Validation Error", "Validation failed.",
                              "VALIDATION_ERROR",
                              errors={"email": ["Enter a valid email address."]})),
        429: resp("Cooldown active, or throttled.",
                  err_example("OTP Cooldown",
                              "Please wait before requesting another OTP.",
                              "OTP_COOLDOWN", details={"retry_after": 45}),
                  THROTTLED_EXAMPLE),
        503: resp("Email could not be sent.",
            err_example("Email Failed", "Could not send the email. Please try again.",
                        "EMAIL_SEND_FAILED")),
    },
)
class ResendRegistrationOTPApi(APIView):
    authentication_classes = []
    throttle_classes = [OTPRateThrottle]

    def post(self, request):
        serializer = ResendRegistrationOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Validation failed.", "VALIDATION_ERROR",
                errors=serializer.errors,
            )

        email = serializer.validated_data["email"]

        cooldown_key = f"registration_resend:{email}"
        otp_key = f"registration_otp:{email}"
        data_key = f"registration_data:{email}"

        registration_data = cache.get(data_key)
        if not registration_data:
            return error_response(
                "Registration session expired. Please register again.",
                "REGISTRATION_EXPIRED",
            )

        if not cache.add(cooldown_key, True, timeout=60):
            return error_response(
                "Please wait before requesting another OTP.", "OTP_COOLDOWN",
                details={"retry_after": max(cache.ttl(cooldown_key), 0)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        otp = str(secrets.randbelow(900000) + 100000)

        try:
            send_mail(
                "Kosh Email Verification OTP",
                f"Your Kosh email verification OTP is {otp}. "
                "This OTP is valid for 5 minutes.",
                None,
                [email],
            )
        except Exception:
            cache.delete(cooldown_key)
            return error_response(
                "Could not send the email. Please try again.", "EMAIL_SEND_FAILED",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        cache.delete(f"registration_attempts:{email}")
        cache.set(otp_key, otp, timeout=300)
        cache.set(data_key, registration_data, timeout=300)

        return success_response("OTP has been resent to your email.")

@extend_schema(
    summary="Invite Employee",
    description=(
        "Owner only. Creates a pending invite for the email, with an optional phone "
        "number for the owner's reference. The person must register (or log in) with "
        "that email and accept the invite. Invites expire after 14 days."
    ),
    request=InviteEmployeeSerializer,
    responses={
        201: resp("Invite created.",
                  ok_example("Invite Created", "Invite created.",
                             data={"id": 1, "email": "ravi@example.com",
                                   "phone": "9876543210", "status": "pending"})),
        400: resp("Validation error, self-invite, or invite limit.",
                  err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR",
                              errors={"phone": ["Enter a valid 10-digit phone number."]}),
                  err_example("Self Invite", "You cannot invite yourself.", "CANNOT_INVITE_SELF"),
                  err_example("Limit Reached", "Too many pending invites. Cancel some first.",
                              "INVITE_LIMIT_REACHED")),
        401: UNAUTHORIZED_RESPONSE,
        403: resp("Not a business owner.",
                  err_example("Not Owner", "Only business owners can manage employees.",
                              "NOT_BUSINESS_OWNER")),
        409: resp("Already invited, or already an employee here.",
                  err_example("Invite Exists", "This email already has a pending invite.",
                              "INVITE_EXISTS"),
                  err_example("Already Employee", "This person already works for your business.",
                              "ALREADY_EMPLOYEE")),
        429: resp("Too many requests.", THROTTLED_EXAMPLE),
    },
)
class InviteEmployeeApi(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [InviteEmployeeThrottle]

    def post(self, request):
        business = get_owned_business(request.user)
        if business is None:
            return error_response(
                "Only business owners can manage employees.", "NOT_BUSINESS_OWNER",
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InviteEmployeeSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Validation failed.", "VALIDATION_ERROR", errors=serializer.errors,
            )
        email = serializer.validated_data["email"]
        phone = serializer.validated_data.get("phone", "")

        if email == (request.user.email or "").lower():
            return error_response("You cannot invite yourself.", "CANNOT_INVITE_SELF")

        if Employee.objects.filter(business=business, user__email__iexact=email).exists():
            return error_response(
                "This person already works for your business.", "ALREADY_EMPLOYEE",
                status=status.HTTP_409_CONFLICT,
            )

        purge_expired_invites(business)  # expired rows must go first, or they block re-inviting

        pending = EmployeeInvite.objects.filter(business=business, status="pending")
        if pending.count() >= 20:
            return error_response(
                "Too many pending invites. Cancel some first.", "INVITE_LIMIT_REACHED",
            )

        try:
            with transaction.atomic():
                invite = EmployeeInvite.objects.create(
                    business=business, email=email, phone=phone
                )
        except IntegrityError:
            return error_response(
                "This email already has a pending invite.", "INVITE_EXISTS",
                status=status.HTTP_409_CONFLICT,
            )

        try:
            send_mail(
                f"You've been invited to join {business.business_name} on Kosh",
                (
                    f"{business.business_name} has invited you to join their team on Kosh.\n\n"
                    f"Sign up or log in with this email address ({invite.email}), "
                    "choose the Employee option, and accept the invite:\n"
                    f"{settings.FRONTEND_URL}/signup\n\n"
                    f"This invite expires in {INVITE_TTL.days} days."
                ),
                None,
                [invite.email],
            )
        except Exception:
            logger.exception("Employee invite email failed")

        return success_response(
            "Invite created.",
            data={"id": invite.id, "email": invite.email,
                  "phone": invite.phone, "status": invite.status},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="List Employees and Pending Invites",
    description="Owner only. Returns the business's employees and its pending invites.",
    responses={
        200: resp("Employees and invites.",
                  ok_example("Employees", "Employees retrieved.",
                             data={"employees": [{"id": 1, "name": "Ravi", "email": "ravi@example.com",
                                                  "phone": "9876543210",
                                                  "joined_at": "2026-10-04T10:00:00Z"}],
                                   "invites": [{"id": 2, "email": "sita@example.com", "phone": "",
                                                "created_at": "2026-10-04T10:05:00Z"}]})),
        401: UNAUTHORIZED_RESPONSE,
        403: resp("Not a business owner.",
                  err_example("Not Owner", "Only business owners can manage employees.",
                              "NOT_BUSINESS_OWNER")),
    },
)
class EmployeeListApi(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request):
        business = get_owned_business(request.user)
        if business is None:
            return error_response(
                "Only business owners can manage employees.", "NOT_BUSINESS_OWNER",
                status=status.HTTP_403_FORBIDDEN,
            )

        purge_expired_invites(business)

        employees = Employee.objects.filter(business=business).select_related("user__profile")
        invites = EmployeeInvite.objects.filter(business=business, status="pending")

        return success_response("Employees retrieved.", data={
            "employees": [
                {"id": e.id, "name": e.user.profile.name, "email": e.user.email,
                 "phone": e.phone, "joined_at": e.created_at}
                for e in employees
            ],
            "invites": [
                {"id": i.id, "email": i.email, "phone": i.phone, "created_at": i.created_at}
                for i in invites
            ],
        })


@extend_schema(
    summary="Cancel Pending Invite",
    description="Owner only. Deletes a pending invite of the owner's business.",
    request=None,
    responses={
        200: resp("Invite cancelled.", ok_example("Cancelled", "Invite cancelled.")),
        401: UNAUTHORIZED_RESPONSE,
        403: resp("Not a business owner.",
                  err_example("Not Owner", "Only business owners can manage employees.",
                              "NOT_BUSINESS_OWNER")),
        404: resp("No such pending invite.",
                  err_example("Not Found", "Invite not found.", "INVITE_NOT_FOUND")),
    },
)
class CancelInviteApi(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def delete(self, request, invite_id):
        business = get_owned_business(request.user)
        if business is None:
            return error_response(
                "Only business owners can manage employees.", "NOT_BUSINESS_OWNER",
                status=status.HTTP_403_FORBIDDEN,
            )
        deleted, _ = EmployeeInvite.objects.filter(
            id=invite_id, business=business, status="pending"
        ).delete()
        if not deleted:
            return error_response(
                "Invite not found.", "INVITE_NOT_FOUND", status=status.HTTP_404_NOT_FOUND,
            )
        return success_response("Invite cancelled.")


@extend_schema(
    summary="Remove Employee",
    description="Owner only. Removes an employee from the owner's business.",
    request=None,
    responses={
        200: resp("Employee removed.", ok_example("Removed", "Employee removed.")),
        401: UNAUTHORIZED_RESPONSE,
        403: resp("Not a business owner.",
                  err_example("Not Owner", "Only business owners can manage employees.",
                              "NOT_BUSINESS_OWNER")),
        404: resp("No such employee.",
                  err_example("Not Found", "Employee not found.", "EMPLOYEE_NOT_FOUND")),
    },
)
class RemoveEmployeeApi(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def delete(self, request, employee_id):
        business = get_owned_business(request.user)
        if business is None:
            return error_response(
                "Only business owners can manage employees.", "NOT_BUSINESS_OWNER",
                status=status.HTTP_403_FORBIDDEN,
            )
        deleted, _ = Employee.objects.filter(id=employee_id, business=business).delete()
        if not deleted:
            return error_response(
                "Employee not found.", "EMPLOYEE_NOT_FOUND", status=status.HTTP_404_NOT_FOUND,
            )
        return success_response("Employee removed.")

@extend_schema(
    summary="My Pending Invites",
    description=(
        "Pending, unexpired employee invites addressed to the logged-in user's email. "
        "Call this only after the user chose the Employee path."
    ),
    responses={
        200: resp("Pending invites.",
                  ok_example("Invites", "Invites retrieved.",
                             data={"invites": [{"id": 1, "business_name": "Kosh Technologies",
                                                "created_at": "2026-10-04T10:00:00Z"}]})),
        401: UNAUTHORIZED_RESPONSE,
    },
)
class MyInvitesApi(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request):
        invites = EmployeeInvite.objects.filter(
            email__iexact=request.user.email, status="pending",
            created_at__gte=invite_cutoff(),
        ).select_related("business")
        return success_response("Invites retrieved.", data={
            "invites": [
                {"id": i.id, "business_name": i.business.business_name,
                 "created_at": i.created_at}
                for i in invites
            ]
        })


@extend_schema(
    summary="Accept Invite",
    description=(
        "Accepts a pending invite addressed to the logged-in user's email and makes "
        "them an employee of that business. Fails if they already own or work for a business."
    ),
    request=None,
    responses={
        200: resp("Invite accepted.",
                  ok_example("Accepted", "Invite accepted.",
                             data={"role": "employee",
                                   "business": {"id": 1, "business_name": "Kosh Technologies"}})),
        401: UNAUTHORIZED_RESPONSE,
        404: resp("No such pending invite for this user.",
                  err_example("Not Found", "Invite not found.", "INVITE_NOT_FOUND")),
        409: resp("User already has a role.",
                  err_example("Already Owner", "You already own a business.", "ALREADY_OWNER"),
                  err_example("Already Employee", "You already work for a business.",
                              "ALREADY_EMPLOYEE")),
    },
)
class AcceptInviteApi(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request, invite_id):
        user = request.user
        try:
            with transaction.atomic():
                invite = (
                    EmployeeInvite.objects.select_for_update()
                    .filter(id=invite_id, email__iexact=user.email,
                            status="pending", created_at__gte=invite_cutoff())
                    .first()
                )
                if invite is None:
                    return error_response(
                        "Invite not found.", "INVITE_NOT_FOUND",
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if Business.objects.filter(owner=user).exists():
                    return error_response(
                        "You already own a business.", "ALREADY_OWNER",
                        status=status.HTTP_409_CONFLICT,
                    )
                if Employee.objects.filter(user=user).exists():
                    return error_response(
                        "You already work for a business.", "ALREADY_EMPLOYEE",
                        status=status.HTTP_409_CONFLICT,
                    )

                business = invite.business
                Employee.objects.create(user=user, business=business, phone=invite.phone)
                EmployeeInvite.objects.filter(email__iexact=user.email).delete()
        except IntegrityError:
            return error_response(
                "You already work for a business.", "ALREADY_EMPLOYEE",
                status=status.HTTP_409_CONFLICT,
            )

        return success_response("Invite accepted.", data={
            "role": "employee",
            "business": {"id": business.id, "business_name": business.business_name},
        })


@extend_schema(
    summary="Decline Invite",
    description="Declines (deletes) a pending invite addressed to the logged-in user's email.",
    request=None,
    responses={
        200: resp("Invite declined.", ok_example("Declined", "Invite declined.")),
        401: UNAUTHORIZED_RESPONSE,
        404: resp("No such pending invite for this user.",
                  err_example("Not Found", "Invite not found.", "INVITE_NOT_FOUND")),
    },
)
class DeclineInviteApi(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request, invite_id):
        deleted, _ = EmployeeInvite.objects.filter(
            id=invite_id, email__iexact=request.user.email, status="pending"
        ).delete()
        if not deleted:
            return error_response(
                "Invite not found.", "INVITE_NOT_FOUND", status=status.HTTP_404_NOT_FOUND,
            )
        return success_response("Invite declined.")
