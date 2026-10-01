from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Business
from .serializers import (
  RegisterSerializer,
  LoginSerializer,
  ForgotPasswordSerializer,
  VerifyResetOTPSerializer,
  ResetPasswordSerializer,
  ChangePasswordSerializer,
  BusinessRegistrationSerializer,
  VerifyRegistrationOTPSerializer,

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
from django.core.mail import send_mail
from django.core.cache import cache
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.conf import settings

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
    },
)
class RegisterApi(APIView):
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

        if cache.get(cooldown_key):
            ttl = cache.ttl(cooldown_key)

            return error_response("Please wait before requesting another OTP.", "OTP_COOLDOWN", 
                                  details={"retry_after": max(ttl, 0)}, 
                                  status=status.HTTP_429_TOO_MANY_REQUESTS)

        otp = str(secrets.randbelow(900000) + 100000)

        cache.delete(f"registration_attempts:{email}")

        cache.set(
            otp_key,
            otp,
            timeout=300
        )

        cache.set(
            data_key,
            {
                "name": name,
                "email": email,
                "password": make_password(password),
            },
            timeout=300
        )

        cache.set(
            cooldown_key,
            True,
            timeout=60
        )

        send_mail(
            "Kosh Email Verification OTP",
            (
                f"Your Kosh email verification OTP is {otp}. "
                "This OTP is valid for 5 minutes."
            ),
            None,
            [email],
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

        if submitted_otp != stored_otp:
            attempts += 1

            cache.set(
                attempts_key,
                attempts,
                timeout=300
            )

            return error_response("Invalid OTP.", "INVALID_OTP", 
                                  details={"remaining_attempts": 5 - attempts})

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
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": False})),
        400: resp("Invalid credentials or validation error.",
                err_example("Invalid Credentials", "Invalid email or password.", "INVALID_CREDENTIALS",
                            errors={"non_field_errors": ["Invalid email or password."]}),
                err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"email": ["This field is required."]})),
        429: resp("Too many login attempts.", THROTTLED_EXAMPLE),
    },
)
class LoginApi(APIView):
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
                        "has_business": has_business},
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
                            data={"id": 1, "name": "John Doe", "email": "john@example.com"})),
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
    })



@extend_schema(
    summary="Logout User",
    description="Logs out the currently authenticated user using the refresh token.",
    request=None,
    responses={
        200: resp("Logout successful. The refresh cookie is cleared.",
                ok_example("Logout Success", "Logout successful.")),
        401: UNAUTHORIZED_RESPONSE,
    },
)

class LogoutApi(APIView):
  permission_classes = [IsAuthenticated]
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



            send_mail(
                "Kosh Password Reset OTP",
                f"Your password reset OTP is {otp}. "
                "This OTP is valid for 5 minutes.",
                None,
                [email],
            )

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
    },
)
class ResetPasswordApi(APIView):

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
    },
)
class ChangePasswordApi(APIView):

    permission_classes=[ IsAuthenticated]

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
        
        user.set_password(new_password)
        user.save()

        user.profile.token_version += 1
        user.profile.save(update_fields=["token_version"])

        for outstanding_token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(
                token=outstanding_token
            )

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
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": False}),
                ok_example("Google Login With Business", "Login successful.",
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": True})),
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
        },
    )
    set_refresh_cookie(response, refresh)
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
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": False}),
                ok_example("Github Login With Business", "Login successful.",
                            data={"access": "eyJhbGciOiJIUzI1NiIs...", "has_business": True})),
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
            },
        )
        set_refresh_cookie(response, refresh)
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
                            "BUSINESS_EXISTS")),
    },
)
class BusinessRegistration(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes=[BusinessRegistrationThrottle]
  def post(self, request):
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
