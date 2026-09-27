from django.contrib.auth.models import User
from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
import re


USERNAME_REGEX = r'^[a-zA-Z0-9_]{3,50}$'

PASSWORD_REGEX = (
    r'^(?=.*[a-z])'
    r'(?=.*[A-Z])'
    r'(?=.*\d)'
    r'(?=.*[@$!%*?&#])'
    r'[A-Za-z\d@$!%*?&#]{8,30}$'
)

class RegisterSerializer(serializers.ModelSerializer):
  username = serializers.RegexField(
      regex=USERNAME_REGEX,
      required=True
  )
  email = serializers.EmailField(required=True)
  password = serializers.RegexField(
      regex=PASSWORD_REGEX,
      required=True,
      write_only=True
  )
  class Meta:
    model = User
    fields = ('username','email','password')

  def validate_username(self, value):
    if User.objects.filter(username=value).exists():
      raise serializers.ValidationError("Username already exists.")
    return value

  def validate_email(self,value):
    if User.objects.filter(email=value).exists():
      raise serializers.ValidationError("Email already exists")
    return value

  def create(self,validated_data):
    user = User.objects.create_user(
      username = validated_data['username'],
      email = validated_data['email'],
      password = validated_data['password'],
    ) 
    return user
  
  



class LoginSerializer(serializers.Serializer):
  identifier = serializers.CharField(required=True)
  password = serializers.CharField(required=True,write_only=True)

  def validate(self,data):
    identifier = data.get('identifier')
    password = data.get('password')
    if '@' in identifier:
      user = User.objects.filter(email=identifier).first()
      if user is None:
        raise serializers.ValidationError("Invalid username/email or password.")
      username = user.username
    else:
      username = identifier


    user = authenticate(username=username,password=password)
    if user is None:
      raise serializers.ValidationError('Invalid Username Or Password.')

    if not user.is_active:
      raise serializers.ValidationError('User account is disabled.')

    refresh = RefreshToken.for_user(user)
    refresh["token_version"] = user.profile.token_version

    return{
      'refresh': str(refresh),
      'access': str(refresh.access_token),
    }

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
