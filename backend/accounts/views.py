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
  LogoutSerializer,
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
from django.db import IntegrityError
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
)
from rest_framework.throttling import (UserRateThrottle)
from django.shortcuts import redirect

REFRESH_COOKIE = "refresh_token"

def set_refresh_cookie(response, refresh_token):
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=str(refresh_token),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,               
        secure=not settings.DEBUG,   
        samesite="Lax",    
        path="/accounts/",
    )

class CookieTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        raw_refresh = request.COOKIES.get(REFRESH_COOKIE)
        if not raw_refresh:
            return Response(
                {"detail": "No refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = TokenRefreshSerializer(data={"refresh": raw_refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken):
            response = Response(
                {"detail": "Invalid or expired token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            response.delete_cookie(REFRESH_COOKIE, path="/accounts/")
            return response

        data = serializer.validated_data
        response = Response({"access": data["access"]})
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
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Registration OTP sent successfully.",
            examples=[
                OpenApiExample(
                    "OTP Sent",
                    value={
                        "message": "OTP has been sent to your email."
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Validation error.",
            examples=[
                OpenApiExample(
                    "Duplicate Email",
                    value={
                        "email": [
                            "Email already exists"
                        ]
                    },
                    response_only=True,
                ),
            ],
        ),
        429: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="OTP resend cooldown is active.",
            examples=[
                OpenApiExample(
                    "Cooldown Active",
                    value={
                        "error": "Please wait before requesting another OTP.",
                        "cooldown_remaining": 43
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class RegisterApi(APIView):
    throttle_classes=[RegisterRateThrottle]
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data["email"]
        name = serializer.validated_data["name"]
        password = serializer.validated_data["password"]

        cooldown_key = f"registration_resend:{email}"
        otp_key = f"registration_otp:{email}"
        data_key = f"registration_data:{email}"

        if cache.get(cooldown_key):
            ttl = cache.ttl(cooldown_key)

            return Response(
                {
                    "error": "Please wait before requesting another OTP.",
                    "cooldown_remaining": max(ttl, 0)
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

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

        return Response(
            {
                "message": "OTP has been sent to your email."
            },
            status=status.HTTP_200_OK
        )

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
        201: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Email verified and user registered successfully.",
            examples=[
                OpenApiExample(
                    "Registration Success",
                    value={
                        "message": (
                            "Email verified and registration successful."
                        )
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid or expired OTP, or registration conflict.",
            examples=[
                OpenApiExample(
                    "Invalid OTP",
                    value={
                        "error": "Invalid OTP.",
                        "remaining_attempts": 4
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Expired OTP",
                    value={
                        "error": "OTP has expired. Please register again."
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Registration Conflict",
                    value={
                        "error": "Email already exists."
                    },
                    response_only=True,
                ),
            ],
        ),
        429: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Maximum OTP verification attempts exceeded.",
            examples=[
                OpenApiExample(
                    "Too Many Attempts",
                    value={
                        "error": (
                            "Too many incorrect OTP attempts. "
                            "Please register again."
                        )
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)

class VerifyRegistrationOTPApi(APIView):
    throttle_classes=[VerifyOTPThrottle]
    def post(self, request):
        serializer = VerifyRegistrationOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data["email"]
        submitted_otp = serializer.validated_data["otp"]

        otp_key = f"registration_otp:{email}"
        data_key = f"registration_data:{email}"
        attempts_key = f"registration_attempts:{email}"

        stored_otp = cache.get(otp_key)
        registration_data = cache.get(data_key)

        if not stored_otp or not registration_data:
            return Response(
                {
                    "error": "OTP has expired. Please register again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        attempts = cache.get(attempts_key, 0)

        if attempts >= 5:
            cache.delete(otp_key)
            cache.delete(data_key)
            cache.delete(attempts_key)

            return Response(
                {
                    "error": (
                        "Too many incorrect OTP attempts. "
                        "Please register again."
                    )
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        if submitted_otp != stored_otp:
            attempts += 1

            cache.set(
                attempts_key,
                attempts,
                timeout=300
            )

            return Response(
                {
                    "error": "Invalid OTP.",
                    "remaining_attempts": 5 - attempts
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.create(
                username=registration_data["email"],
                email=registration_data["email"],
                password=registration_data["password"],
            )
            user.profile.name = registration_data["name"]
            user.profile.save(update_fields=["name"])

        except IntegrityError:
            return Response(
                {
                    "error": "Email already exists."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        cache.delete(otp_key)
        cache.delete(data_key)
        cache.delete(attempts_key)
        cache.delete(f"registration_resend:{email}")

        return Response(
            {
                "message": "Email verified and registration successful."
            },
            status=status.HTTP_201_CREATED
        )


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
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Login successful.",
            examples=[
                OpenApiExample(
                    "Login Success",
                    value={
                        "success": True,
                        "message": "Login successful.",
                        "refresh": "eyJhbGciOiJIUzI1NiIs...",
                        "access": "eyJhbGciOiJIUzI1NiIs...",
                        "has_business": False
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid credentials.",
            examples=[
                OpenApiExample(
                    "Invalid Credentials",
                    value={
                        "success": False,
                        "errors": {
                            "non_field_errors": [
                                "Invalid email or password."
                            ]
                        }
                    },
                    response_only=True,
                ),
            ],
        ),
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
      response=Response({
        "success": True,
        "message": "Login successful.",
        "access": data["access"],
        "has_business": has_business,
        },status=status.HTTP_200_OK
      )
      set_refresh_cookie(response, data["refresh"])
      return response
    return Response({
      "success": False,
      "errors": serializer.errors
      },status=status.HTTP_400_BAD_REQUEST
    )


@extend_schema(
    summary="Get User Profile",
    description="Retrieve the profile information of the currently authenticated user.",
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Profile retrieved successfully.",
            examples=[
                OpenApiExample(
                    "Profile Success",
                    value={
                        "id": 1,
                        "email": "john@example.com",
                        "name": "John Doe"
                    },
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Authentication credentials were not provided or are invalid.",
            examples=[
                OpenApiExample(
                    "Unauthorized",
                    value={
                        "detail": "Authentication credentials were not provided."
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class ProfileApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes=[UserRateThrottle]
  def get(self,request):
    user =request.user
    return Response({
      "id":user.id,
      "name":user.profile.name,
      "email":user.email,
    }, status=status.HTTP_200_OK)



@extend_schema(
    summary="Logout User",
    description="Logs out the currently authenticated user using the refresh token.",
    request=LogoutSerializer,
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Logout successful.",
            examples=[
                OpenApiExample(
                    "Logout Success",
                    value={
                        "message": "Logout successful."
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid or missing refresh token.",
            examples=[
                OpenApiExample(
                    "Missing Refresh Token",
                    value={
                        "error": "Refresh token is required."
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Invalid Refresh Token",
                    value={
                        "error": "Invalid refresh token."
                    },
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Authentication credentials were not provided or are invalid.",
            examples=[
                OpenApiExample(
                    "Unauthorized",
                    value={
                        "detail": "Authentication credentials were not provided."
                    },
                    response_only=True,
                ),
            ],
        ),
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

    response = Response({
      'message': 'Logout successful.'
      }, status=status.HTTP_200_OK
    )
    response.delete_cookie(REFRESH_COOKIE, path="/accounts/")
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
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Password reset OTP sent successfully.",
            examples=[
                OpenApiExample(
                    "OTP Sent",
                    value={
                        "message": "If an account exists with this email, "
                                   "a password reset OTP has been sent."
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid request or email address.",
            examples=[
                OpenApiExample(
                    "Invalid Email",
                    value={
                        "email": [
                            "User with this email does not exist."
                        ]
                    },
                    response_only=True,
                ),
            ],
        ),
        429: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Too many OTP requests.",
            examples=[
                OpenApiExample(
                    "OTP Cooldown",
                    value={
                        "message": "Please wait before requesting another OTP.",
                        "retry_after": 45
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class ForgotPasswordApi(APIView):
    throttle_classes=[ForgotPasswordRateThrottle]
    def post(self, request):

        serializer = ForgotPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data["email"].lower()

        cooldown_key = f"password_reset_resend:{email}"

        retry_after = cache.ttl(cooldown_key)

        if retry_after > 0:
            return Response(
                {
                    "message": "Please wait before requesting another OTP.",
                    "retry_after": retry_after
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        user = User.objects.filter(email__iexact=email).first()

        if user:

            otp = str(secrets.randbelow(900000) + 100000)

            otp_key = f"password_reset_otp:{email}"

            cache.set(
                otp_key,
                otp,
                timeout=300
            )

            cache.set(
                cooldown_key,
                True,
                timeout=60
            )

            send_mail(
                "Kosh Password Reset OTP",
                f"Your password reset OTP is {otp}. "
                "This OTP is valid for 5 minutes.",
                None,
                [email],
            )

        return Response(
            {
                "message": "If an account exists with this email, "
                           "a password reset OTP has been sent."
            },
            status=status.HTTP_200_OK
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
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="OTP verified successfully.",
            examples=[
                OpenApiExample(
                    "OTP Verified",
                    value={
                        "message": "OTP verified successfully.",
                        "reset_token": "example-reset-token"
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid or expired OTP.",
            examples=[
                OpenApiExample(
                    "Invalid OTP",
                    value={
                        "error": "Invalid OTP.",
                        "attempts_remaining": 4
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Expired OTP",
                    value={
                        "error": "OTP has expired or is invalid."
                    },
                    response_only=True,
                ),
            ],
        ),
        429: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Too many incorrect OTP attempts.",
            examples=[
                OpenApiExample(
                    "Too Many Attempts",
                    value={
                        "error": "Too many incorrect attempts. "
                                 "Please request a new OTP."
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class VerifyResetOTPApi(APIView):
    throttle_classes=[VerifyOTPThrottle]
    def post(self, request):

        serializer = VerifyResetOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data["email"].lower()
        otp = serializer.validated_data["otp"]

        otp_key = f"password_reset_otp:{email}"
        attempts_key = f"password_reset_attempts:{email}"

        stored_otp = cache.get(otp_key)

        if stored_otp is None:
            return Response(
                {
                    "error": "OTP has expired or is invalid."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        attempts = cache.get(attempts_key, 0)

        if attempts >= 5:
            cache.delete(otp_key)
            cache.delete(attempts_key)

            return Response(
                {
                    "error": "Too many incorrect attempts. "
                             "Please request a new OTP."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        if not secrets.compare_digest(str(stored_otp), otp):

            attempts += 1

            if attempts >= 5:
                cache.delete(otp_key)
                cache.delete(attempts_key)

                return Response(
                    {
                        "error": "Too many incorrect attempts. "
                                "Please request a new OTP."
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            cache.set(
                attempts_key,
                attempts,
                timeout=300
            )

            return Response(
                {
                    "error": "Invalid OTP.",
                    "attempts_remaining": 5 - attempts
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(email__iexact=email).first()

        if user is None:
            return Response(
                {
                    "error": "Invalid OTP."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        reset_token = secrets.token_urlsafe(32)

        reset_token_key = f"password_reset_token:{reset_token}"

        cache.set(
            reset_token_key,
            user.id,
            timeout=600
        )

        cache.delete(otp_key)
        cache.delete(attempts_key)

        return Response(
            {
                "message": "OTP verified successfully.",
                "reset_token": reset_token
            },
            status=status.HTTP_200_OK
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
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Password reset successfully.",
            examples=[
                OpenApiExample(
                    "Password Reset Success",
                    value={
                        "message": "Password reset successfully."
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid reset token or passwords do not match.",
            examples=[
                OpenApiExample(
                    "Invalid Reset Token",
                    value={
                        "error": "Invalid or expired reset token."
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Password Validation Error",
                    value={
                        "new_password": [
                            "Passwords do not match."
                        ]
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class ResetPasswordApi(APIView):

    def post(self, request):

        serializer = ResetPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        reset_token = serializer.validated_data["reset_token"]
        new_password = serializer.validated_data["new_password"]

        reset_token_key = f"password_reset_token:{reset_token}"

        user_id = cache.get(reset_token_key)

        if user_id is None:
            return Response(
                {
                    "error": "Invalid or expired reset token."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(id=user_id).first()

        if user is None:
            cache.delete(reset_token_key)

            return Response(
                {
                    "error": "Invalid or expired reset token."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        cache.delete(reset_token_key)

        return Response(
            {
                "message": "Password reset successfully."
            },
            status=status.HTTP_200_OK
        )


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
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Password changed successfully.",
            examples=[
                OpenApiExample(
                    "Password Change Success",
                    value={
                        "message": "Password changed successfully."
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid current password or passwords do not match.",
            examples=[
                OpenApiExample(
                    "Incorrect Current Password",
                    value={
                        "error": "Current Password is incorrect."
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Password Validation Error",
                    value={
                        "new_password": [
                            "Passwords do not match."
                        ]
                    },
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Authentication credentials were not provided or are invalid.",
            examples=[
                OpenApiExample(
                    "Unauthorized",
                    value={
                        "detail": "Authentication credentials were not provided."
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class ChangePasswordApi(APIView):

    permission_classes=[ IsAuthenticated]

    def post(self, request):
        serializer=ChangePasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        user=request.user

        current_password=serializer.validated_data["current_password"]
        new_password=serializer.validated_data["new_password"]

        if not user.check_password(current_password):
            return Response({
               "error": "Current Password is incorrect."
            },
            status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save()

        user.profile.token_version += 1
        user.profile.save(update_fields=["token_version"])

        for outstanding_token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(
                token=outstanding_token
            )

        return Response({
           "message": "Password changed successfuly."
        }, status=status.HTTP_200_OK)


@extend_schema(
    summary="Generate JWT for Google User",
    description=(
        "Generates access and refresh JWT tokens for a user "
        "authenticated through Google OAuth."
    ),
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="JWT tokens generated successfully.",
            examples=[
                OpenApiExample(
                    "Google Login Without Business",
                    value={
                        "refresh": "eyJhbGciOiJIUzI1NiIs...",
                        "access": "eyJhbGciOiJIUzI1NiIs...",
                        "has_business": False
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Google Login With Business",
                    value={
                        "refresh": "eyJhbGciOiJIUzI1NiIs...",
                        "access": "eyJhbGciOiJIUzI1NiIs...",
                        "has_business": True
                    },
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Google authentication failed.",
            examples=[
                OpenApiExample(
                    "Google Authentication Failed",
                    value={
                        "error": "Google authentication failed."
                    },
                    response_only=True,
                ),
            ],
        ),
    },
    tags=["Authentication"],
)
class GoogleJWTApi(APIView):
  throttle_classes=[OAuthRateThrottle]
  def post(self, request):
    user = request.user
    if not user.is_authenticated:
      return Response({"error": "Google authentication failed."
        },status=status.HTTP_401_UNAUTHORIZED
      )

    refresh = RefreshToken.for_user(user)
    refresh["token_version"] = user.profile.token_version
    has_business = Business.objects.filter(owner=request.user).exists()

    response = Response({
      "access": str(refresh.access_token),
      "has_business": has_business,
      }, status=status.HTTP_200_OK
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
        201: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Business registered successfully.",
            examples=[
                OpenApiExample(
                    "Business Registration Success",
                    value={
                        "success": True,
                        "message": "Business registered successfully.",
                        "data": {
                            "id": 1,
                            "business_name": "Kosh Technologies",
                            "business_type": "Retail",
                            "city": "Ghaziabad"
                        }
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid business details or business already registered.",
            examples=[
                OpenApiExample(
                    "Business Already Registered",
                    value={
                        "success": False,
                        "message": "Business is already registered."
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Invalid Business Details",
                    value={
                        "success": False,
                        "errors": {
                            "business_name": [
                                "This field may not be blank."
                            ]
                        }
                    },
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Authentication credentials were not provided or are invalid.",
            examples=[
                OpenApiExample(
                    "Unauthorized",
                    value={
                        "detail": "Authentication credentials were not provided."
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class BusinessRegistration(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes=[BusinessRegistrationThrottle]
  def post(self, request):
    if Business.objects.filter(owner=request.user).exists():
      return Response({
        "success": False,
        "message": "Business is already registered."
        },status=status.HTTP_400_BAD_REQUEST
      )
    serializer = BusinessRegistrationSerializer(data=request.data)
    if serializer.is_valid():
      business = serializer.save(owner=request.user)
      return Response({
        "success": True,
        "message": "Business registered successfully.",
        "data": {
          "id": business.id,
          "business_name": business.business_name,
          "business_type": business.business_type,
          "city": business.city
          }
        },status=status.HTTP_201_CREATED
      )

    return Response({
      "success": False,
      "errors": serializer.errors
      },status=status.HTTP_400_BAD_REQUEST
    )
