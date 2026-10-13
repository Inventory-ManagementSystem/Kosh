from django.urls import path
from . import views

urlpatterns = [
  path("rfqs/", views.RFQListApi.as_view(), name="rfq-list"),
  path("rfqs/summary/", views.RFQSummaryApi.as_view(), name="rfq-summary"),
  path("rfqs/<uuid:pk>/", views.RFQDetailApi.as_view(), name="rfq-detail"),
  path("rfqs/<uuid:pk>/cancel/", views.RFQCancelApi.as_view(), name="rfq-cancel"),
  path("alerts/", views.ReorderAlertListApi.as_view(), name="reorder-alert-list"),
]
