from django.contrib.auth.models import User
from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken


class RegisterSerializer(serializers.ModelSerializer):
  username = serializers.CharField(required=True)
  email = serializers.EmailField(required=True)
  password = serializers.CharField(required=True,write_only=True)
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

    return{
      'refresh': str(refresh),
      'access': str(refresh.access_token),
    }

