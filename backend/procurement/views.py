from django.shortcuts import render

# Create your views here.

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.pagination import StandardPagination
from accounts.permissions import HasBusinessAccess, IsOwner
from accounts.responses import error_response, success_response, validation_error_response
from accounts.swagger import UNAUTHORIZED_RESPONSE, ok_example, resp
from suppliers.permissions import IsSupplier
from django.db import transaction
from notifications.models import Notification
from notifications.services import notify_many
from .alert_services import create_alerts_for_business
from .ranking import WeightError, parse_weights, rank_quotations

from .SwaggerDocs import (
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
  reorder_alert_create_rfq_docs,
  reorder_alert_dismiss_docs,
  reorder_alert_bulk_create_rfq_docs,
  reorder_alert_refresh_docs,
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
  BulkRFQCreateSerializer, 
  RFQCreateSerializer,
)
from .services import (
  QuotationError,
  decline_rfq,
  ensure_rfq_accepting,
  mark_viewed,
  submit_quotation,
  withdraw_quotation,
)

from .rfq_services import (
  RFQCreationError,
  create_rfq_for_suggestion,
  create_rfqs_for_suggestions,
)

from .serializers import RFQCreateSerializer

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
    .select_related("supply_category")
    .prefetch_related(
      "items__product__category","items__product__supply_category", "recipients__supplier_profile", "reorder_suggestions"
    )
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

    with transaction.atomic():
      rfq.status = RFQ.Status.CANCELLED
      rfq.save(update_fields=["status", "updated_at"])

      ReorderSuggestion.objects.filter(
        rfq=rfq, status=ReorderSuggestion.Status.RFQ_CREATED
      ).update(
        status=ReorderSuggestion.Status.OPEN,
        rfq=None,
        updated_at=timezone.now(),
      )

      recipients = rfq.recipients.select_related("supplier_profile__user").exclude(
        status=RFQRecipient.Status.DECLINED
      )
      notify_many(
        [r.supplier_profile.user for r in recipients],
        f"RFQ {rfq.number} was cancelled",
        f"{request.business.business_name} cancelled this request. "
        "You don't need to send a quotation.",
        kind=Notification.Kind.RFQ,
        push=False,
      )

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
      .select_related("product__category", "product__supply_category")
    )
    return paginated_response(request, qs, ReorderAlertSerializer, "Alerts fetched.")


@reorder_alert_refresh_docs
class ReorderAlertRefreshApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def post(self, request):
    created = create_alerts_for_business(request.business, notify=False)
    active = ReorderSuggestion.objects.filter(
      business=request.business, status__in=ReorderSuggestion.ACTIVE
    ).count()
    return success_response(
      "Alerts refreshed.", {"created": created, "active_alerts": active}
    )

def supplier_rfq_queryset(supplier):
  return (
    RFQRecipient.objects.filter(supplier_profile=supplier)
    .select_related("rfq__business", "rfq__supply_category", "quotation")
    .prefetch_related("rfq__items__product", "quotation__items__rfq_item")
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
    quotations = list(
      rfq.quotations.exclude(status=Quotation.Status.WITHDRAWN)
      .select_related("rfq", "supplier_profile", "recipient")
      .prefetch_related("items__rfq_item", "rfq__items__product")
    )
    try:
      ranked = rank_quotations(quotations, parse_weights(request.query_params))
    except WeightError as err:
      return error_response(err.message, err.code, status=status.HTTP_400_BAD_REQUEST)

    ordered = ranked
    if request.query_params.get("sort") == "price":
      ordered = sorted(
        ranked, key=lambda r: (r["quotation"].grand_total, r["quotation"].submitted_at)
      )
    return success_response(
      "Quotations fetched.",
      OwnerQuotationSerializer(
        [r["quotation"] for r in ordered],
        many=True,
        context={"ranking": {r["quotation"].pk: r for r in ranked}},
      ).data,
    )


@reorder_alert_create_rfq_docs
class ReorderAlertCreateRFQApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def post(self, request, pk):
    suggestion = get_object_or_404(ReorderSuggestion, pk=pk, business=request.business)
    serializer = RFQCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
      rfq = create_rfq_for_suggestion(
        suggestion,
        quantity=serializer.validated_data.get("quantity"),
        include_platform_pool=serializer.validated_data["include_platform_pool"],
        created_by=request.user,
      )
    except RFQCreationError as exc:
      return Response(
        {"success": False, "message": exc.message, "code": exc.code, "errors": None, "details": None},
        status=409 if exc.code == "SUGGESTION_NOT_OPEN" else 400,
      )
    rfq = rfq_queryset(request.business).get(pk=rfq.pk)
    return Response(
      {"success": True, "message": "RFQ created.", "data": RFQDetailSerializer(rfq).data},
      status=201,
    )

BULK_RFQ_ERROR_STATUS = {"ALERT_NOT_FOUND": 404, "SUGGESTION_NOT_OPEN": 409}


@reorder_alert_bulk_create_rfq_docs
class ReorderAlertBulkCreateRFQApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def post(self, request):
    serializer = BulkRFQCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
      rfqs = create_rfqs_for_suggestions(
        request.business,
        [(a["id"], a.get("quantity")) for a in data["alerts"]],
        include_platform_pool=data["include_platform_pool"],
        created_by=request.user,
      )
    except RFQCreationError as exc:
      return error_response(
        exc.message, exc.code, status=BULK_RFQ_ERROR_STATUS.get(exc.code, 400)
      )
    qs = rfq_queryset(request.business).filter(pk__in=[r.pk for r in rfqs]).order_by("number")
    return success_response(
      "RFQs created.", RFQDetailSerializer(qs, many=True).data,
      status=status.HTTP_201_CREATED,
    )

@reorder_alert_dismiss_docs
class ReorderAlertDismissApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def post(self, request, pk):
    suggestion = get_object_or_404(ReorderSuggestion, pk=pk, business=request.business)
    if suggestion.status != ReorderSuggestion.Status.OPEN:
      return Response(
        {
          "success": False,
          "message": "Only an alert without an RFQ can be dismissed.",
          "code": "SUGGESTION_NOT_OPEN",
          "errors": None,
          "details": None,
        },
        status=409,
      )
    suggestion.status = ReorderSuggestion.Status.CLOSED
    suggestion.save(update_fields=["status", "updated_at"])
    return Response({"success": True, "message": "Alert dismissed.", "data": None})
