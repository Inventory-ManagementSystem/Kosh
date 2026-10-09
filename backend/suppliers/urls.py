from django.urls import path
from . import views

urlpatterns = [
  path("register/", views.SupplierRegistrationApi.as_view(), name="supplier-register"),
  path("supplier-profile/", views.MySupplierProfileApi.as_view(), name="supplier-me"),
  path("categories/", views.SupplyCategoryListApi.as_view(), name="supply-category-list"),
]
