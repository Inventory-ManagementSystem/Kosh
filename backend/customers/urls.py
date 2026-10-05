from django.urls import path
from .views import CustomerListCreateApi, CustomerDetailApi

urlpatterns = [
  path("", CustomerListCreateApi.as_view(), name="customer-list-create"),
  path("<uuid:pk>/", CustomerDetailApi.as_view(), name="customer-detail"),
]
