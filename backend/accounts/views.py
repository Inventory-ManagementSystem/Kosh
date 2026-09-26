from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RegisterSerializer, LoginSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken


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