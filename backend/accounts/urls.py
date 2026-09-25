from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
  path('register/',views.RegisterApi.as_view(),name='register_api'),
  path('login/',views.LoginApi.as_view(),name='login_api'),
  path('token/refresh/',TokenRefreshView.as_view(),name='token_refresh'),
  path('profile/',views.ProfileApi.as_view(),name='profile_api'),
  path('logout/',views.LogoutApi.as_view(),name='logout_api')
]