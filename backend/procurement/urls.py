from django.urls import path
from . import views

urlpatterns = [
  path("rfqs/", views.RFQListApi.as_view(), name="rfq-list"),
  path("rfqs/summary/", views.RFQSummaryApi.as_view(), name="rfq-summary"),
  path("rfqs/<uuid:pk>/", views.RFQDetailApi.as_view(), name="rfq-detail"),
  path("rfqs/<uuid:pk>/cancel/", views.RFQCancelApi.as_view(), name="rfq-cancel"),
  path("rfqs/<uuid:pk>/quotations/", views.RFQQuotationListApi.as_view(), name="rfq-quotation-list"),
  path("alerts/", views.ReorderAlertListApi.as_view(), name="reorder-alert-list"),

  path("supplier/rfqs/", views.SupplierRFQListApi.as_view(), name="supplier-rfq-list"),
  path("supplier/rfqs/<uuid:pk>/", views.SupplierRFQDetailApi.as_view(), name="supplier-rfq-detail"),
  path("supplier/rfqs/<uuid:pk>/quotation/", views.SupplierQuotationApi.as_view(), name="supplier-quotation"),
  path("supplier/rfqs/<uuid:pk>/decline/", views.SupplierRFQDeclineApi.as_view(), name="supplier-rfq-decline"),
  path("alerts/<uuid:pk>/create-rfq/", views.ReorderAlertCreateRFQApi.as_view(), name="reorder-alert-create-rfq"),
  path("alerts/create-rfq/", views.ReorderAlertBulkCreateRFQApi.as_view(), name="reorder-alert-bulk-create-rfq"),
  path("alerts/<uuid:pk>/dismiss/", views.ReorderAlertDismissApi.as_view(), name="reorder-alert-dismiss"),
  path("alerts/refresh/", views.ReorderAlertRefreshApi.as_view(), name="reorder-alert-refresh"),
  path("quotations/<uuid:pk>/accept/", views.QuotationAcceptApi.as_view(), name="quotation-accept"),
  path("orders/<uuid:pk>/cancel/", views.PurchaseOrderCancelApi.as_view(), name="order-cancel"),
  path("orders/", views.PurchaseOrderListApi.as_view(), name="order-list"),
  path("orders/<uuid:pk>/", views.PurchaseOrderDetailApi.as_view(), name="order-detail"),
  path("supplier/orders/", views.SupplierPurchaseOrderListApi.as_view(), name="supplier-order-list"),
  path("supplier/orders/<uuid:pk>/", views.SupplierPurchaseOrderDetailApi.as_view(), name="supplier-order-detail"),
  path("supplier/orders/<uuid:pk>/dispatch/", views.SupplierPurchaseOrderDispatchApi.as_view(), name="supplier-order-dispatch"),
  path("invoices/", views.InvoiceListApi.as_view(), name="invoice-list"),
  path("invoices/<uuid:pk>/", views.InvoiceDetailApi.as_view(), name="invoice-detail"),
  path("supplier/invoices/", views.SupplierInvoiceListApi.as_view(), name="supplier-invoice-list"),
  path("supplier/invoices/<uuid:pk>/", views.SupplierInvoiceDetailApi.as_view(), name="supplier-invoice-detail"),
  
]
