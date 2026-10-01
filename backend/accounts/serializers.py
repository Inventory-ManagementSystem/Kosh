from django.contrib.auth.models import User
from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Business
import re


NAME_REGEX = r'^[A-Za-z ]+$'

PASSWORD_REGEX = (
    r'^(?=.*[a-z])'
    r'(?=.*[A-Z])'
    r'(?=.*\d)'
    r'(?=.*[@$!%*?&#])'
    r'[A-Za-z\d@$!%*?&#]{8,30}$'
)

class RegisterSerializer(serializers.ModelSerializer):
  name = serializers.RegexField(
    regex=NAME_REGEX,
    min_length=2,
    max_length=50,
    required=True,
    error_messages={
      "invalid": "Name can contain only letters and single spaces.",
      "min_length": "Name must be at least 2 characters long.",
      "max_length": "Name cannot exceed 50 characters."
    }
  )
  email = serializers.EmailField(required=True)
  password = serializers.RegexField(
      regex=PASSWORD_REGEX,
      required=True,
      write_only=True
  )
  class Meta:
    model = User
    fields = ('name','email','password')

  def validate_name(self, value):
    return " ".join(value.split())

  def validate_email(self,value):
    if User.objects.filter(email=value).exists():
      raise serializers.ValidationError("Email already exists")
    return value

class VerifyRegistrationOTPSerializer(serializers.Serializer):
  email = serializers.EmailField(required=True)

  otp = serializers.CharField(
      required=True,
      min_length=6,
      max_length=6
  )
  
  



class LoginSerializer(serializers.Serializer):
  email = serializers.EmailField(required=True)
  password = serializers.CharField(required=True,write_only=True)

  def validate(self, data):
    email = data.get("email")
    password = data.get("password")

    user = User.objects.filter(email__iexact=email).first()

    if user is None:
      raise serializers.ValidationError("Invalid email or password.")

    user = authenticate(
      username=user.username,
      password=password
    )

    if user is None:
      raise serializers.ValidationError(
        "Invalid email or password."
      )

    if not user.is_active:
      raise serializers.ValidationError(
        "User account is disabled."
      )

    refresh = RefreshToken.for_user(user)
    refresh["token_version"] = user.profile.token_version

    return {
      "refresh": str(refresh),
      "access": str(refresh.access_token),
      "user": user,
    }


class BusinessRegistrationSerializer(serializers.ModelSerializer):
  class Meta:
    model = Business
    fields = ["business_name","business_type","city",]
  def validate_business_name(self, value):
    if not value.strip():
      raise serializers.ValidationError("Business name cannot be empty.")
    return value
class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(
        min_length=6,
        max_length=6
    )


class ResetPasswordSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    new_password = serializers.RegexField(
        regex=PASSWORD_REGEX,
        required=True,
        write_only=True
    )
    confirm_password = serializers.RegexField(
        regex=PASSWORD_REGEX,
        required=True,
        write_only=True
    )

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        return data

class ChangePasswordSerializer(serializers.Serializer):
   current_password=serializers.CharField(
      required=True,
      write_only=True
   )

   new_password=serializers.RegexField(
      regex=PASSWORD_REGEX,
      required=True,
      write_only=True
   )

   confirm_password=serializers.RegexField(
      regex=PASSWORD_REGEX,
      required=True,
      write_only=True
   )

   def validate(self, data):
      if data["new_password"]!=data["confirm_password"]:
         raise serializers.ValidationError({
            "confirm password": "passwords do not match."
         })

      return data

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)
