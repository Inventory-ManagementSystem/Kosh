from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RegisterSerializer, LoginSerializer, BusinessRegistrationSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Business


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



class GoogleJWTApi(APIView):
  def get(self, request):
    user = request.user
    if not user.is_authenticated:
      return Response({"error": "Google authentication failed."
        },status=status.HTTP_401_UNAUTHORIZED
      )

    refresh = RefreshToken.for_user(user)
    has_business = Business.objects.filter(owner=request.user).exists()

    return Response({
      "refresh": str(refresh),
      "access": str(refresh.access_token),
      "has_business": has_business,
      },status=status.HTTP_200_OK
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