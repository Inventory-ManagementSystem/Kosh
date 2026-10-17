from django.urls import path
from . import views

urlpatterns = [
  path("rfqs/", views.RFQListApi.as_view(), name="rfq-list"),
  path("rfqs/summary/", views.RFQSummaryApi.as_view(), name="rfq-summary"),
  path("rfqs/<uuid:pk>/", views.RFQDetailApi.as_view(), name="rfq-detail"),
  path("rfqs/<uuid:pk>/cancel/", views.RFQCancelApi.as_view(), name="rfq-cancel"),
  path("rfqs/<uuid:pk>/quotations/", views.RFQQuotationListApi.as_view(), name="rfq-quotation-list"),
  path("rfqs/<uuid:pk>/pdf/", views.RFQPdfApi.as_view(), name="rfq-pdf"),
  path("quotations/<uuid:pk>/pdf/", views.QuotationPdfApi.as_view(), name="quotation-pdf"),
  path("alerts/", views.ReorderAlertListApi.as_view(), name="reorder-alert-list"),

  path("supplier/rfqs/", views.SupplierRFQListApi.as_view(), name="supplier-rfq-list"),
  path("supplier/rfqs/<uuid:pk>/", views.SupplierRFQDetailApi.as_view(), name="supplier-rfq-detail"),
  path("supplier/rfqs/<uuid:pk>/quotation/", views.SupplierQuotationApi.as_view(), name="supplier-quotation"),
  path("supplier/rfqs/<uuid:pk>/decline/", views.SupplierRFQDeclineApi.as_view(), name="supplier-rfq-decline"),
  path("supplier/rfqs/<uuid:pk>/pdf/", views.SupplierRFQPdfApi.as_view(), name="supplier-rfq-pdf"),
  path("supplier/rfqs/<uuid:pk>/quotation/pdf/",views.SupplierQuotationPdfApi.as_view(), name="supplier-quotation-pdf",),
]