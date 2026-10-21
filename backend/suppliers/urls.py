from django.urls import path
from . import views

urlpatterns = [
  path("register/", views.SupplierRegistrationApi.as_view(), name="supplier-register"),
  path("supplier-profile/", views.MySupplierProfileApi.as_view(), name="supplier-me"),
  path("categories/", views.SupplyCategoryListApi.as_view(), name="supply-category-list"),
  path("my-suppliers/", views.OwnerSupplierListCreateApi.as_view(), name="owner-supplier-list"),
  path("my-suppliers/<uuid:pk>/", views.OwnerSupplierDetailApi.as_view(), name="owner-supplier-detail"),
  path("payout-account/", views.SupplierPayoutAccountApi.as_view(), name="supplier-payout-account"),
]
