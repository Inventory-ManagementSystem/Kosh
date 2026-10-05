from django.urls import path
from . import views


urlpatterns = [
  path("products/",views.ProductListCreateApi.as_view(),name="product-list",),

  path("products/<uuid:pk>/",views.ProductDetailApi.as_view(),name="product-detail",),
  path("products/<uuid:pk>/adjust-stock/",views.ProductAdjustStockApi.as_view(),name="product-adjust-stock",),

  path("categories/",views.CategoryListCreateApi.as_view(),name="category-list",),
  path("categories/<uuid:pk>/",views.CategoryDetailApi.as_view(),name="category-detail",),

  path("warehouses/",views.WarehouseListCreateApi.as_view(),name="warehouse-list",),
  path("warehouses/<uuid:pk>/",views.WarehouseDetailApi.as_view(),name="warehouse-detail",),
]