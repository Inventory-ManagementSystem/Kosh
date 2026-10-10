from django.urls import path
from . import views


urlpatterns = [
  path("products/",views.ProductListCreateApi.as_view(),name="product-list",),

  path("products/<uuid:pk>/",views.ProductDetailApi.as_view(),name="product-detail",),
  path("products/<uuid:pk>/adjust-stock/",views.ProductAdjustStockApi.as_view(),name="product-adjust-stock",),

  path("categories/",views.CategoryListCreateApi.as_view(),name="category-list",),
  path("categories/<uuid:pk>/",views.CategoryDetailApi.as_view(),name="category-detail",),

  path("warehouse/",views.WarehouseApi.as_view(),name="warehouse",),

  path("outlets/",views.OutletListCreateApi.as_view(),name="outlet-list",),
  path("outlets/<uuid:pk>/",views.OutletDetailApi.as_view(),name="outlet-detail",),

  path("dispatches/",views.DispatchListCreateApi.as_view(),name="dispatch-list",),
  path("dispatches/<uuid:pk>/",views.DispatchDetailApi.as_view(),name="dispatch-detail",),

]