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
)
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
import secrets
from rest_framework_simplejwt.token_blacklist.models import (
    OutstandingToken,
    BlacklistedToken,
)

from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.cache import cache

from drf_spectacular.utils import (extend_schema,OpenApiResponse,OpenApiExample)


@extend_schema(
    summary="Register User",
    request=RegisterSerializer,
    examples=[
        OpenApiExample(
            "Valid Registration",
            summary="Successful registration",
            description="Use this data to test a successful user registration.",
            value={
                "username": "john_doe",
                "email": "john@example.com",
                "password": "John@1234"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Another Valid User",
            summary="Second test user",
            description="Another valid registration payload.",
            value={
                "username": "alice_smith",
                "email": "alice@example.com",
                "password": "Alice@1234"
            },
            request_only=True,
        ),
        OpenApiExample(
            "Duplicate Username",
            summary="Test duplicate username",
            description="Use this after john_doe has already been registered.",
            value={
                "username": "john_doe",
                "email": "newuser@example.com",
                "password": "NewUser@1234"
            },
            request_only=True,
        ),
    ],
    responses={
        201: OpenApiResponse(
            description="User registered successfully.",
            examples=[
                OpenApiExample(
                    "Registration Success",
                    value={
                        "message": "User Registered Successfully"
                    },
                )
            ],
        ),
        400: OpenApiResponse(
            description="Validation error.",
            examples=[
                OpenApiExample(
                    "Validation Error",
                    value={
                        "username": [
                            "Username already exists."
                        ]
                    },
                )
            ],
        ),
    },
)
class RegisterApi(APIView):
  def post(self,request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response({
        'message': 'User Registered Successfully'
      },
      status=status.HTTP_201_CREATED)

    return Response(
      serializer.errors,
      status = status.HTTP_400_BAD_REQUEST
    )


@extend_schema(
    summary="Login User",
    request=LoginSerializer,
    examples=[
        OpenApiExample(
            "Login with Email",
            summary="Login using email",
            value={
                "identifier": "john@example.com",
                "password": "John@1234",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Login with Username",
            summary="Login using username",
            value={
                "identifier": "john_doe",
                "password": "John@1234",
            },
            request_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="Login successful.",
            examples=[
                OpenApiExample(
                    "Login Success",
                    value={
                        "success": True,
                        "message": "Login successful.",
                        "refresh": "eyJhbGciOiJIUzI1NiIs...",
                        "access": "eyJhbGciOiJIUzI1NiIs...",
                        "has_business": False,
                    },
                )
            ],
        ),
        400: OpenApiResponse(
            description="Invalid credentials.",
            examples=[
                OpenApiExample(
                    "Invalid Credentials",
                    value={
                        "success": False,
                        "errors": {
                            "non_field_errors": [
                                "Invalid Username Or Password."
                            ]
                        }
                    },
                )
            ],
        ),
    },
)
class LoginApi(APIView):
  def post(self,request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
      data=serializer.validated_data
      user= data["user"]
      has_business = Business.objects.filter(owner=user).exists()
      return Response({
        "success": True,
        "message": "Login successful.",
        "refresh": data["refresh"],
        "access": data["access"],
        "has_business": has_business,
        },status=status.HTTP_200_OK
      )

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
            description="Profile retrieved successfully.",
            examples=[
                OpenApiExample(
                    "Profile Success",
                    value={
                        "username": "john_doe",
                        "email": "john@example.com",
                    },
                ),
            ],
        ),
        401: OpenApiResponse(
            description="Authentication credentials were not provided or are invalid.",
            examples=[
                OpenApiExample(
                    "Unauthorized",
                    value={
                        "detail": "Authentication credentials were not provided."
                    },
                ),
            ],
        ),
    },
)
class ProfileApi(APIView):
  permission_classes = [IsAuthenticated]
  def get(self,request):
    user =request.user
    return Response({
      "id":user.id,
      "email":user.email,
      "username":user.username,
    }, status=status.HTTP_200_OK)



@extend_schema(
    summary="Logout User",
    description="Logs out the currently authenticated user.",
    responses={
        200: OpenApiResponse(
            description="Logout successful.",
            examples=[
                OpenApiExample(
                    "Logout Success",
                    value={
                        "message": "Logout successful."
                    },
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Invalid logout request.",
        ),
        401: OpenApiResponse(
            description="Authentication credentials were not provided or are invalid.",
        ),
    },
)
class LogoutApi(APIView):
  permission_classes = [IsAuthenticated]
  def post(self, request):
    refresh_token = request.data.get('refresh')
    if not refresh_token:
      return Response({
        'error': 'Refresh token is required.'
        },status=status.HTTP_400_BAD_REQUEST
      )
    try:
      token = RefreshToken(refresh_token)
      token.blacklist()
      return Response({
        'message': 'Logout successful.'
        },status=status.HTTP_200_OK
        )

    except Exception:
      return Response({
        'error': 'Invalid refresh token.'
        },status=status.HTTP_400_BAD_REQUEST
      )


@extend_schema(
    summary="Request Password Reset",
    description="Sends a password reset OTP to the user's registered email address.",

    request=ForgotPasswordSerializer,

    examples=[
        OpenApiExample(
            "Forgot Password Request",
            summary="Request password reset",
            value={
                "email": "john@example.com"
            },
            request_only=True,
        ),
    ],

    responses={
        200: OpenApiResponse(
            description="Password reset OTP sent successfully.",
            examples=[
                OpenApiExample(
                    "OTP Sent",
                    value={
                        "message": "OTP sent successfully."
                    },
                ),
            ],
        ),

        400: OpenApiResponse(
            description="Invalid request or email address.",
            examples=[
                OpenApiExample(
                    "Invalid Email",
                    value={
                        "email": [
                            "User with this email does not exist."
                        ]
                    },
                ),
            ],
        ),
    },
)
class ForgotPasswordApi(APIView):

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
            "Verify OTP",
            value={
                "email": "john@example.com",
                "otp": "123456"
            },
            request_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="OTP verified successfully."
        ),
        400: OpenApiResponse(
            description="Invalid or expired OTP."
        ),
    },
)
class VerifyResetOTPApi(APIView):

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
            "Reset Password",
            summary="Reset password with reset token",
            value={
                "reset_token": "example-reset-token",
                "new_password": "NewPassword@123",
                "confirm_password": "NewPassword@123",
            },
            request_only=True,
        ),
    ],

    responses={
        200: OpenApiResponse(
            description="Password reset successfully."
        ),
        400: OpenApiResponse(
            description="Invalid reset token or passwords do not match."
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
            "Change Password",
            summary="Change user's password",
            value={
                "current_password": "OldPassword@123",
                "new_password": "NewPassword@123",
                "confirm_password": "NewPassword@123",
            },
            request_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="Password changed successfully."
        ),
        400: OpenApiResponse(
            description="Invalid current password or passwords do not match."
        ),
        401: OpenApiResponse(
            description="Authentication credentials were not provided or are invalid."
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
            description="JWT tokens generated successfully."
        ),
        401: OpenApiResponse(
            description="Google authentication failed."
        ),
    },
    tags=["Authentication"],
)
class GoogleJWTApi(APIView):
  def get(self, request):
    user = request.user
    if not user.is_authenticated:
      return Response({"error": "Google authentication failed."
        },status=status.HTTP_401_UNAUTHORIZED
      )

    refresh = RefreshToken.for_user(user)
    has_business = Business.objects.filter(owner=request.user).exists()
    refresh["token_version"] = user.profile.token_version

    return Response({
      "refresh": str(refresh),
      "access": str(refresh.access_token),
      "has_business": has_business,
      },status=status.HTTP_200_OK
    )



@extend_schema(
    summary="Register Business",
    description="Creates business details for the authenticated business owner.",

    request=BusinessRegistrationSerializer,

    examples=[
        OpenApiExample(
            "Business Registration",
            summary="Register a business",
            value={
                "business_name": "Kosh Technologies",
                "business_type": "Retail",
                "city": "Ghaziabad",
            },
            request_only=True,
        ),
    ],

    responses={
        201: OpenApiResponse(
            description="Business registered successfully."
        ),
        400: OpenApiResponse(
            description="Invalid business details."
        ),
        401: OpenApiResponse(
            description="Authentication credentials were not provided or are invalid."
        ),
    },
)
class BusinessRegistration(APIView):
  permission_classes = [IsAuthenticated]
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
