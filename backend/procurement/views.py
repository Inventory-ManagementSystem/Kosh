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
from notifications import events
from .alert_services import create_alerts_for_business
from .ranking import WeightError, parse_weights, rank_quotations
from .dispatch_services import mark_dispatched
from notifications.models import Notification
from notifications.services import notify_many


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
  po_accept_docs,
  po_advance_docs,
  po_advance_verify_docs,
  po_cancel_docs,
  po_cancel_docs,
  po_list_docs,
  po_detail_docs,
  supplier_po_list_docs,
  supplier_po_detail_docs,
  supplier_po_dispatch_docs,
  invoice_list_docs,
  invoice_detail_docs,
  supplier_invoice_list_docs,
  supplier_invoice_detail_docs,
  payout_list_docs,
  supplier_payout_list_docs,

)

from .models import RFQ, Quotation, RFQRecipient, ReorderSuggestion, PurchaseOrder, Shipment, Invoice, Payout
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
  PurchaseOrderSummarySerializer,
  PurchaseOrderSummarySerializer,
  PurchaseOrderListSerializer,
  PurchaseOrderDetailSerializer,
  SupplierPurchaseOrderListSerializer,
  DispatchSerializer,
  ShipmentSerializer,
  InvoiceSummarySerializer,
  InvoiceListSerializer,
  InvoiceDetailSerializer,
  PayoutSerializer,

)
from .payout_services import PayoutWebhookError, PayoutError, handle_payout_webhook
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

from .throttles import QuotationWriteThrottle, OrderWriteThrottle

from .po_services import PurchaseOrderError, accept_quotation, cancel_unpaid_order

import logging
from django.conf import settings
from rest_framework.permissions import AllowAny
from .payment_services import (
  PaymentError, WebhookError, handle_webhook,
  start_advance_payment, to_paise, verify_advance_payment,
)
from .serializers import AdvanceVerifySerializer, PaymentSerializer

logger = logging.getLogger(__name__)

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
    before = {field: getattr(rfq, field) for field in ("deadline", "notes")}
    serializer.save()
    rfq = self._get_rfq(request, pk)  # reload with prefetches
    changed = [field for field, old in before.items() if getattr(rfq, field) != old]
    if changed:
      events.rfq_updated(rfq, changed)
    return Response({
      "success": True,
      "message": "RFQ updated.",
      "data": RFQDetailSerializer(rfq).data,
    })

@rfq_cancel_docs
class RFQCancelApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def post(self, request, pk):
    with transaction.atomic():
      rfq = get_object_or_404(
        RFQ.objects.select_for_update(), pk=pk, business=request.business
      )
      if rfq.status not in (RFQ.Status.OPEN, RFQ.Status.CLOSED):
        return error_response(
          "Only an open or closed RFQ can be cancelled.",
          "RFQ_NOT_OPEN",
          status=status.HTTP_400_BAD_REQUEST,
        )

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
    created = create_alerts_for_business(request.business)
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

PO_ERROR_STATUS = {
  "QUOTATION_NOT_FOUND": 404,
  "ORDER_NOT_FOUND": 404,
  "RFQ_ALREADY_AWARDED": 409,
  "RFQ_CANCELLED": 409,
  "QUOTATION_NOT_ACTIVE": 409,
  "ORDER_CANCELLED": 409,
  "ORDER_NOT_FOUND": 404,
  "PAYMENT_NOT_FOUND": 404,
  "ADVANCE_ALREADY_PAID": 409,
  "ADVANCE_EXPIRED": 409,
  "NO_ADVANCE_DUE": 409,
  "PAYMENT_NOT_CAPTURED": 409,
  "ORDER_MISMATCH": 400,
  "INVALID_SIGNATURE": 400,
  "AMOUNT_MISMATCH": 400,
  "GATEWAY_ERROR": 502,
  "PAYMENTS_NOT_CONFIGURED": 503,
  "ORDER_NOT_CANCELLABLE": 409,
  "PAYMENT_RECEIVED": 409,
  "ALREADY_DISPATCHED": 409,
}
 
 
def po_error_response(err):
  return error_response(
    err.message, err.code,
    status=PO_ERROR_STATUS.get(err.code, status.HTTP_400_BAD_REQUEST),
  )
 
 
@po_accept_docs
class QuotationAcceptApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]
  throttle_classes = [OrderWriteThrottle]
 
  def post(self, request, pk):
    try:
      po = accept_quotation(request.business, pk)
    except PurchaseOrderError as err:
      return po_error_response(err)
 
    po = PurchaseOrder.objects.select_related("supplier_profile", "rfq").get(pk=po.pk)
    if po.status == PurchaseOrder.Status.ISSUED:
      message = "Quotation accepted and order issued."
    else:
      message = "Quotation accepted. Pay the advance to confirm the order."
    return success_response(
      message, PurchaseOrderSummarySerializer(po).data, status=status.HTTP_201_CREATED
    )


def _owner_po(request, pk):
  return (
    PurchaseOrder.objects.select_related("supplier_profile", "rfq")
    .filter(pk=pk, business=request.business)
    .first()
  )

@po_advance_docs
class AdvancePaymentApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]
  throttle_classes = [OrderWriteThrottle]

  def get(self, request, pk):
    po = _owner_po(request, pk)
    if po is None:
      return error_response("Purchase order not found.", "ORDER_NOT_FOUND", status=404)
    return success_response("Advance status.", {
      "order": PurchaseOrderSummarySerializer(po).data,
      "payments": PaymentSerializer(po.payments.all(), many=True).data,
    })

  def post(self, request, pk):
    try:
      po, payment = start_advance_payment(request.business, pk)
    except PaymentError as err:
      return po_error_response(err)

    user = request.user
    profile_name = getattr(getattr(user, "profile", None), "name", "") or ""
    return success_response("Checkout ready.", {
      "key": settings.RAZORPAY_KEY_ID,
      "order_id": payment.razorpay_order_id,
      "amount": to_paise(payment.amount),  
      "currency": "INR",
      "name": "Kosh",
      "description": f"Advance for {po.number} - {po.supplier_profile.company_name}",
      "prefill": {"name": profile_name, "email": user.email},
      "notes": {"purchase_order_id": str(po.pk)},
      "purchase_order_id": str(po.pk),
      "advance_due_by": po.advance_due_by,
    })

@po_advance_verify_docs
class AdvancePaymentVerifyApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]
  throttle_classes = [OrderWriteThrottle]

  def post(self, request, pk):
    serializer = AdvanceVerifySerializer(data=request.data)
    if not serializer.is_valid():
      return validation_error_response(serializer)
    data = serializer.validated_data
    try:
      po = verify_advance_payment(
        request.business, pk,
        data["razorpay_order_id"], data["razorpay_payment_id"], data["razorpay_signature"],
      )
    except PaymentError as err:
      return po_error_response(err)

    po = PurchaseOrder.objects.select_related("supplier_profile", "rfq").get(pk=po.pk)
    if po.status == PurchaseOrder.Status.ISSUED:
      message = "Advance paid. The order has been sent to the supplier."
    else:
      message = "Payment received, but this order was already closed. It will be refunded."
    return success_response(message, PurchaseOrderSummarySerializer(po).data)


@extend_schema(exclude=True)
class RazorpayWebhookApi(APIView):
  authentication_classes = []
  permission_classes = [AllowAny]
  throttle_classes = []

  def post(self, request):
    raw = request.body 
    signature = request.headers.get("X-Razorpay-Signature", "")
    try:
      result = handle_webhook(raw, signature)
    except WebhookError:
      return Response({"detail": "invalid signature"}, status=status.HTTP_400_BAD_REQUEST)
    except PaymentError as err:
      if err.code == "GATEWAY_ERROR":
        return Response({"detail": "retry"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
      logger.error("Razorpay webhook not applied: %s (%s)", err.message, err.code)
      return Response({"status": "logged"})
    except Exception:
      logger.exception("Razorpay webhook crashed")
      return Response({"detail": "error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({"status": result})
@po_cancel_docs
class PurchaseOrderCancelApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]
  throttle_classes = [OrderWriteThrottle]

  def post(self, request, pk):
    try:
      po = cancel_unpaid_order(request.business, pk)
    except PurchaseOrderError as err:
      return po_error_response(err)

    po = PurchaseOrder.objects.select_related("supplier_profile", "rfq").get(pk=po.pk)
    return success_response(
      "Order cancelled. The quotation can be accepted again.",
      PurchaseOrderSummarySerializer(po).data,
    )

def po_queryset(base):
  return (
    base.select_related(
      "rfq", "business__owner__profile", "supplier_profile__user", "shipment", "invoice"
    )
    .prefetch_related(
      "items__product__category", "items__product__supply_category", "payments",
      "shipment__items__purchase_order_item",
    )
  )


@po_list_docs
class PurchaseOrderListApi(APIView):
  permission_classes = [HasBusinessAccess]

  def get(self, request):
    qs = po_queryset(PurchaseOrder.objects.filter(business=request.business))
    status_param = request.query_params.get("status")
    if status_param in PurchaseOrder.Status.values:
      qs = qs.filter(status=status_param)
    return paginated_response(request, qs, PurchaseOrderListSerializer, "Orders fetched.")


@po_detail_docs
class PurchaseOrderDetailApi(APIView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    po = get_object_or_404(
      po_queryset(PurchaseOrder.objects.filter(business=request.business)), pk=pk
    )
    return success_response(
      "Order fetched.",
      PurchaseOrderDetailSerializer(po, context={"request": request}).data,
    )


def supplier_po_base(supplier):
  return PurchaseOrder.objects.filter(
    supplier_profile=supplier, status__in=PurchaseOrder.SUPPLIER_VISIBLE
  )


@supplier_po_list_docs
class SupplierPurchaseOrderListApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request):
    qs = po_queryset(supplier_po_base(request.supplier))
    status_param = request.query_params.get("status")
    if status_param in PurchaseOrder.SUPPLIER_VISIBLE:
      qs = qs.filter(status=status_param)
    return paginated_response(
      request, qs, SupplierPurchaseOrderListSerializer, "Orders fetched."
    )


@supplier_po_detail_docs
class SupplierPurchaseOrderDetailApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    po = get_object_or_404(po_queryset(supplier_po_base(request.supplier)), pk=pk)
    return success_response(
      "Order fetched.",
      PurchaseOrderDetailSerializer(po, context={"request": request}).data,
    )

@supplier_po_dispatch_docs
class SupplierPurchaseOrderDispatchApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]
  throttle_classes = [OrderWriteThrottle]

  def post(self, request, pk):
    serializer = DispatchSerializer(data=request.data)
    if not serializer.is_valid():
      return validation_error_response(serializer)
    data = serializer.validated_data

    quantities = None
    if "items" in data:
      quantities = {
        line["purchase_order_item"]: line["quantity"] for line in data["items"]
      }

    try:
      shipment, invoice = mark_dispatched(
        request.supplier,
        pk,
        request.user,
        quantities=quantities,
        expected_delivery_date=data.get("expected_delivery_date"),
        tracking_note=data["tracking_note"],
      )
    except PurchaseOrderError as err:
      return po_error_response(err)

    shipment = Shipment.objects.prefetch_related("items__purchase_order_item").get(
      pk=shipment.pk
    )
    return success_response(
      "Order marked as dispatched. Invoice generated.",
      {
        "shipment": ShipmentSerializer(shipment).data,
        "invoice": InvoiceSummarySerializer(invoice).data,
      },
      status=status.HTTP_201_CREATED,
    )

def invoice_queryset(base):
  return base.select_related(
    "purchase_order__shipment", "business__owner__profile", "supplier_profile__user"
  ).prefetch_related("items")


@invoice_list_docs
class InvoiceListApi(APIView):
  permission_classes = [HasBusinessAccess]

  def get(self, request):
    qs = invoice_queryset(Invoice.objects.filter(business=request.business))
    status_param = request.query_params.get("status")
    if status_param in Invoice.Status.values:
      qs = qs.filter(status=status_param)
    return paginated_response(request, qs, InvoiceListSerializer, "Invoices fetched.")


@invoice_detail_docs
class InvoiceDetailApi(APIView):
  permission_classes = [HasBusinessAccess]

  def get(self, request, pk):
    invoice = get_object_or_404(
      invoice_queryset(Invoice.objects.filter(business=request.business)), pk=pk
    )
    return success_response("Invoice fetched.", InvoiceDetailSerializer(invoice).data)


@supplier_invoice_list_docs
class SupplierInvoiceListApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request):
    qs = invoice_queryset(Invoice.objects.filter(supplier_profile=request.supplier))
    status_param = request.query_params.get("status")
    if status_param in Invoice.Status.values:
      qs = qs.filter(status=status_param)
    return paginated_response(request, qs, InvoiceListSerializer, "Invoices fetched.")


@supplier_invoice_detail_docs
class SupplierInvoiceDetailApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request, pk):
    invoice = get_object_or_404(
      invoice_queryset(Invoice.objects.filter(supplier_profile=request.supplier)), pk=pk
    )
    return success_response("Invoice fetched.", InvoiceDetailSerializer(invoice).data)

def payout_queryset(base):
  return base.select_related("purchase_order", "invoice", "supplier_profile")


def filter_payout_status(request, qs):
  status_param = request.query_params.get("status")
  if status_param in Payout.Status.values:
    qs = qs.filter(status=status_param)
  return qs


@payout_list_docs
class PayoutListApi(APIView):
  permission_classes = [HasBusinessAccess, IsOwner]

  def get(self, request):
    qs = payout_queryset(Payout.objects.filter(purchase_order__business=request.business))
    qs = filter_payout_status(request, qs)
    return paginated_response(request, qs, PayoutSerializer, "Payouts fetched.")


@supplier_payout_list_docs
class SupplierPayoutListApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request):
    qs = payout_queryset(Payout.objects.filter(supplier_profile=request.supplier))
    qs = filter_payout_status(request, qs)
    return paginated_response(request, qs, PayoutSerializer, "Payouts fetched.")


@extend_schema(exclude=True)
class RazorpayXWebhookApi(APIView):
  authentication_classes = []
  permission_classes = [AllowAny]
  throttle_classes = []

  def post(self, request):
    raw = request.body
    signature = request.headers.get("X-Razorpay-Signature", "")
    try:
      result = handle_payout_webhook(raw, signature)
    except PayoutWebhookError:
      return Response({"detail": "invalid signature"}, status=status.HTTP_400_BAD_REQUEST)
    except PayoutError as err:
      logger.error("RazorpayX webhook not applied: %s (%s)", err.message, err.code)
      return Response({"detail": "retry"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception:
      logger.exception("RazorpayX webhook crashed")
      return Response({"detail": "error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({"status": result})
