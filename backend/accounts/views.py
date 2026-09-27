from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import (
  RegisterSerializer,
  LoginSerializer,
  ForgotPasswordSerializer,
  VerifyResetOTPSerializer,
  ResetPasswordSerializer,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
import secrets

from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.cache import cache


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


class LoginApi(APIView):
  def post(self,request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
      return Response(
        serializer.validated_data,
        status=status.HTTP_200_OK
      )

    return Response(
      serializer.errors,
      status=status.HTTP_400_BAD_REQUEST
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
