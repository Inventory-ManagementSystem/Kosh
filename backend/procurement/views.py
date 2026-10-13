from django.shortcuts import render

# Create your views here.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.pagination import StandardPagination
from accounts.permissions import HasBusinessAccess, IsOwner
from accounts.swagger import UNAUTHORIZED_RESPONSE, ok_example, resp

from .SwaggerDocs import (
  reorder_alert_list_docs,
  rfq_cancel_docs,
  rfq_detail_docs,
  rfq_list_docs,
  rfq_summary_docs,
)

from .models import RFQ, ReorderSuggestion
from .serializers import (
  RFQDetailSerializer,
  RFQListSerializer,
  RFQUpdateSerializer,
  ReorderAlertSerializer,
)

def paginated_response(request, queryset, serializer_class, message):
  paginator = StandardPagination()
  paginator.message = message
  page = paginator.paginate_queryset(queryset, request)
  data = serializer_class(page, many=True, context={"request": request}).data
  return paginator.get_paginated_response(data)


def rfq_queryset(business):
  return (
    RFQ.objects.filter(business=business)
    .prefetch_related("items__product__category", "recipients__supplier_profile")
  )

@rfq_list_docs
class RFQListApi(APIView):
  permission_classes = [HasBusinessAccess]

  def get(self, request):
    qs = rfq_queryset(request.business)
    status_param = request.query_params.get("status")
    if status_param in RFQ.Status.values:
      qs = qs.filter(status=status_param)
    return paginated_response(request, qs, RFQListSerializer, "RFQs fetched.")

@rfq_detail_docs
class RFQDetailApi(APIView):
  def get_permissions(self):
    if self.request.method in SAFE_METHODS:
      return [HasBusinessAccess()]
    return [HasBusinessAccess(), IsOwner()]

  def _get_rfq(self, request, pk):
    return get_object_or_404(rfq_queryset(request.business), pk=pk)

  def get(self, request, pk):
    rfq = self._get_rfq(request, pk)
    return Response({
      "success": True,
      "message": "RFQ fetched.",
      "data": RFQDetailSerializer(rfq).data,
    })

  def patch(self, request, pk):
    rfq = self._get_rfq(request, pk)
    serializer = RFQUpdateSerializer(rfq, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    rfq = self._get_rfq(request, pk)  # reload with prefetches
    return Response({
      "success": True,
      "message": "RFQ updated.",
      "data": RFQDetailSerializer(rfq).data,
    })

@rfq_cancel_docs
class RFQCancelApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def post(self, request, pk):
    rfq = get_object_or_404(RFQ, pk=pk, business=request.business)
    if rfq.status != RFQ.Status.OPEN:
      return Response(
        {
          "success": False,
          "message": "Only an open RFQ can be cancelled.",
          "code": "RFQ_NOT_OPEN",
          "errors": None,
          "details": None,
        },
        status=400,
      )
    rfq.status = RFQ.Status.CANCELLED
    rfq.save(update_fields=["status", "updated_at"])
    return Response({"success": True, "message": "RFQ cancelled.", "data": None})

@rfq_summary_docs
class RFQSummaryApi(APIView):
  """The three cards at the top of the RFQ & Alerts screen."""
  permission_classes = [HasBusinessAccess]

  def get(self, request):
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rfqs = RFQ.objects.filter(business=request.business, created_at__gte=month_start)
    return Response({
      "success": True,
      "message": "Summary fetched.",
      "data": {
        "total_monthly_rfq": rfqs.count(),
        "approved_quotations": rfqs.filter(status=RFQ.Status.AWARDED).count(),
        "active_alerts": ReorderSuggestion.objects.filter(
          business=request.business, status__in=ReorderSuggestion.ACTIVE
        ).count(),
      },
    })

@reorder_alert_list_docs
class ReorderAlertListApi(APIView):
  """The Active Alerts table."""
  permission_classes = [HasBusinessAccess]

  def get(self, request):
    qs = (
      ReorderSuggestion.objects
      .filter(business=request.business, status__in=ReorderSuggestion.ACTIVE)
      .select_related("product__category")
    )
    return paginated_response(request, qs, ReorderAlertSerializer, "Alerts fetched.")
