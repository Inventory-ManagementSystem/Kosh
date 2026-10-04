"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from .views import HealthAPIView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/',include("accounts.urls")),
    path('accounts/3rdparty/login/cancelled/',RedirectView.as_view(url="https://koshh.me/oauth/callback?error=cancelled")),
    path('accounts/3rdparty/signup/',RedirectView.as_view(url="https://koshh.me/oauth/callback?error=signup_failed")),
    path('accounts/login/',RedirectView.as_view(url="https://koshh.me/login")),
    path('accounts/signup/',RedirectView.as_view(url="https://koshh.me/signup")),
    path('accounts/3rdparty/login/error/', RedirectView.as_view(url="https://koshh.me/oauth/callback?error=login_failed")),
    path('accounts/',include('allauth.urls')),
    path('inventory/', include('inventory.urls')),
    path('', HealthAPIView.as_view(), name='health'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/',SpectacularSwaggerView.as_view(url_name='schema'),name='swagger-ui'),
]
