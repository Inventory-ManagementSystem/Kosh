from django.urls import path

from .views import GlobalSearchApi

urlpatterns = [
  path("", GlobalSearchApi.as_view(), name="global-search"),
]
