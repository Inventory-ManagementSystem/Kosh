from django.urls import path
from . import views


urlpatterns = [
  path("products/",views.ProductListCreateApi.as_view(),name="product-list",),

  path("products/<uuid:pk>/",views.ProductDetailApi.as_view(),name="product-detail",),
  path("products/<uuid:pk>/adjust-stock/",views.ProductAdjustStockApi.as_view(),name="product-adjust-stock",),
]