from django.shortcuts import render

# Create your views here.

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.pagination import StandardPagination
from accounts.permissions import HasBusinessAccess, IsOwner
from accounts.responses import error_response, success_response, validation_error_response
from accounts.swagger import UNAUTHORIZED_RESPONSE, ok_example, resp
from suppliers.permissions import IsSupplier

from . import pdf
from .renderers import PDFRenderer
from .SwaggerDocs import (
  quotation_pdf_docs,
  rfq_pdf_docs,
  supplier_quotation_pdf_docs,
  supplier_rfq_pdf_docs,
  reorder_alert_list_docs,
  rfq_quotation_list_docs,
  supplier_quotation_docs,
  supplier_rfq_decline_docs,
  supplier_rfq_detail_docs,
  supplier_rfq_list_docs,
  rfq_cancel_docs,
  rfq_detail_docs,
  rfq_list_docs,
  rfq_summary_docs,
)

from .models import RFQ, Quotation, RFQRecipient, ReorderSuggestion
from .serializers import (
  OwnerQuotationSerializer,
  QuotationSerializer,
  QuotationSubmitSerializer,
  RFQDetailSerializer,
  RFQListSerializer,
  RFQUpdateSerializer,
  ReorderAlertSerializer,
  SupplierRFQInboxDetailSerializer,
  SupplierRFQListSerializer,
)
from .services import (
  QuotationError,
  decline_rfq,
  ensure_rfq_accepting,
  mark_viewed,
  submit_quotation,
  withdraw_quotation,
)
from .throttles import QuotationWriteThrottle

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



def supplier_rfq_queryset(supplier):
  return (
    RFQRecipient.objects.filter(supplier_profile=supplier)
    .select_related("rfq__business", "quotation")
    .prefetch_related("rfq__items__product__category", "quotation__items__rfq_item")
    .order_by("-created_at")
  )


def get_invitation(queryset, pk):
  recipient = queryset.filter(pk=pk).first()
  if recipient is None:
    raise NotFound("RFQ not found.")
  return recipient


def quotation_error_response(err):
  return error_response(err.message, err.code, status=status.HTTP_400_BAD_REQUEST)


def quotation_with_relations(**filters):
  return (
    Quotation.objects.filter(**filters)
    .select_related("rfq")
    .prefetch_related("items__rfq_item", "rfq__items__product")
    .first()
  )


@supplier_rfq_list_docs
class SupplierRFQListApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request):
    qs = supplier_rfq_queryset(request.supplier)
    status_param = request.query_params.get("status")
    if status_param in RFQRecipient.Status.values:
      qs = qs.filter(status=status_param)
    if request.query_params.get("open") == "true":
      qs = qs.filter(rfq__status=RFQ.Status.OPEN, rfq__deadline__gt=timezone.now())
    return paginated_response(request, qs, SupplierRFQListSerializer, "RFQs fetched.")


@supplier_rfq_detail_docs
class SupplierRFQDetailApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    recipient = get_invitation(supplier_rfq_queryset(request.supplier), pk)
    mark_viewed(recipient)
    return success_response("RFQ fetched.", SupplierRFQInboxDetailSerializer(recipient).data)


@supplier_quotation_docs
class SupplierQuotationApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]
  throttle_classes = [QuotationWriteThrottle]

  def _recipient(self, request, pk):
    return get_invitation(
      RFQRecipient.objects.filter(supplier_profile=request.supplier).select_related("rfq"),
      pk,
    )

  def get(self, request, pk):
    recipient = self._recipient(request, pk)
    quotation = quotation_with_relations(recipient=recipient)
    if quotation is None:
      return error_response(
        "You have not quoted on this RFQ yet.", "NO_QUOTATION",
        status=status.HTTP_404_NOT_FOUND,
      )
    return success_response("Quotation fetched.", QuotationSerializer(quotation).data)

  def put(self, request, pk):
    recipient = self._recipient(request, pk)
    try:
      ensure_rfq_accepting(recipient.rfq) 
    except QuotationError as err:
      return quotation_error_response(err)

    serializer = QuotationSubmitSerializer(data=request.data, context={"rfq": recipient.rfq})
    if not serializer.is_valid():
      return validation_error_response(serializer)

    try:
      quotation, created = submit_quotation(recipient, serializer.validated_data)
    except QuotationError as err:
      return quotation_error_response(err)

    quotation = quotation_with_relations(pk=quotation.pk)
    return success_response(
      "Quotation submitted." if created else "Quotation revised.",
      QuotationSerializer(quotation).data,
      status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )

  def delete(self, request, pk):
    recipient = self._recipient(request, pk)
    try:
      withdraw_quotation(recipient)
    except QuotationError as err:
      return quotation_error_response(err)
    return success_response("Quotation withdrawn.")


@supplier_rfq_decline_docs
class SupplierRFQDeclineApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]
  throttle_classes = [QuotationWriteThrottle]

  def post(self, request, pk):
    recipient = get_invitation(
      RFQRecipient.objects.filter(supplier_profile=request.supplier), pk
    )
    try:
      decline_rfq(recipient)
    except QuotationError as err:
      return quotation_error_response(err)
    return success_response("RFQ declined.")


@rfq_quotation_list_docs
class RFQQuotationListApi(APIView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    rfq = get_object_or_404(RFQ, pk=pk, business=request.business)
    quotations = (
      rfq.quotations.exclude(status=Quotation.Status.WITHDRAWN)
      .select_related("rfq", "supplier_profile", "recipient")
      .prefetch_related("items__rfq_item", "rfq__items__product")
      .order_by("grand_total", "submitted_at")
    )
    return success_response(
      "Quotations fetched.", OwnerQuotationSerializer(quotations, many=True).data
    )  


def pdf_response(content, filename):
  response = HttpResponse(content, content_type="application/pdf")
  response["Content-Disposition"] = f'attachment; filename="{filename}"'
  return response


def quotation_filename(quotation):
  company = slugify(quotation.supplier_profile.company_name) or "supplier"
  return f"{quotation.rfq.number}-quotation-{company}.pdf"


def quotation_for_pdf(**filters):
  return (
    Quotation.objects.filter(**filters)
    .select_related("rfq__business", "supplier_profile__user")
    .prefetch_related("items__rfq_item", "rfq__items__product")
    .first()
  )


class PDFView(APIView):
  renderer_classes = [JSONRenderer, PDFRenderer]


@rfq_pdf_docs
class RFQPdfApi(PDFView):
  permission_classes = [HasBusinessAccess]
  def get(self, request, pk):
    rfq = get_object_or_404(
      RFQ.objects.select_related("business").prefetch_related("items__product__category"),
      pk=pk, business=request.business,
    )
    return pdf_response(pdf.rfq_pdf(rfq), f"{rfq.number}.pdf")


@quotation_pdf_docs
class QuotationPdfApi(PDFView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    quotation = quotation_for_pdf(pk=pk, rfq__business=request.business)
    if quotation is None or quotation.status == Quotation.Status.WITHDRAWN:
      raise NotFound("Quotation not found.")
    return pdf_response(pdf.quotation_pdf(quotation), quotation_filename(quotation))


@supplier_rfq_pdf_docs
class SupplierRFQPdfApi(PDFView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    recipient = get_invitation(
      RFQRecipient.objects.filter(supplier_profile=request.supplier)
      .select_related("rfq__business")
      .prefetch_related("rfq__items__product__category"),
      pk,
    )
    return pdf_response(pdf.rfq_pdf(recipient.rfq), f"{recipient.rfq.number}.pdf")


@supplier_quotation_pdf_docs
class SupplierQuotationPdfApi(PDFView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    recipient = get_invitation(
      RFQRecipient.objects.filter(supplier_profile=request.supplier), pk
    )
    quotation = quotation_for_pdf(recipient=recipient)
    if quotation is None:
      return error_response(
        "You have not quoted on this RFQ yet.", "NO_QUOTATION",
        status=status.HTTP_404_NOT_FOUND,
      )
    return pdf_response(pdf.quotation_pdf(quotation), quotation_filename(quotation))