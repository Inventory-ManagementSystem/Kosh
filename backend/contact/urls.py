from django.urls import path

from .views import ContactApi

urlpatterns = [
  path("", ContactApi.as_view(), name="contact"),
]
