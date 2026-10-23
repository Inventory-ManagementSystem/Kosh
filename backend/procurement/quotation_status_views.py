from django.db.models import (
  Exists,
  IntegerField,
  OuterRef,
  Prefetch,
  Q,
  Subquery,
  Sum,
)
from django.db.models.functions import Coalesce
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from suppliers.permissions import IsSupplier

from .models import PurchaseOrder, Quotation, QuotationItem
from .quotation_status_docs import supplier_quotation_status_list_docs
from .quotation_status_serializers import SupplierQuotationStatusSerializer
from .views import paginated_response

SEARCH_MAX_LENGTH = 100


def supplier_quotation_queryset(supplier):
  visible_orders = PurchaseOrder.objects.filter(
    quotation=OuterRef("pk"), status__in=PurchaseOrder.SUPPLIER_VISIBLE
  )
  quantity = (
    QuotationItem.objects.filter(quotation=OuterRef("pk"))
    .order_by()
    .values("quotation")
    .annotate(total=Sum("quantity"))
    .values("total")
  )
  return (
    Quotation.objects.filter(supplier_profile=supplier)
    .select_related("rfq__business")
    .annotate(
      total_quantity=Coalesce(
        Subquery(quantity, output_field=IntegerField()),
        0,
        output_field=IntegerField(),
      ),
      has_visible_order=Exists(visible_orders),
    )
    .prefetch_related(
      Prefetch(
        "purchase_orders",
        queryset=PurchaseOrder.objects.filter(
          status__in=PurchaseOrder.SUPPLIER_VISIBLE
        ).order_by("-created_at"),
        to_attr="visible_orders",
      )
    )
    .order_by("-updated_at", "-submitted_at", "-id")
  )


def apply_status_filter(qs, value):
  Status = Quotation.Status
  if value == Status.SUBMITTED:
    return qs.filter(
      Q(status=Status.SUBMITTED)
      | Q(status=Status.ACCEPTED, has_visible_order=False)
    )
  if value == Status.ACCEPTED:
    return qs.filter(status=Status.ACCEPTED, has_visible_order=True)
  if value in Status.values:
    return qs.filter(status=value)
  return qs


def apply_search(qs, term):
  term = (term or "").strip()[:SEARCH_MAX_LENGTH]
  if not term:
    return qs
  order_match = PurchaseOrder.objects.filter(
    quotation=OuterRef("pk"),
    status__in=PurchaseOrder.SUPPLIER_VISIBLE,
    number__icontains=term,
  )
  return qs.filter(
    Q(rfq__number__icontains=term)
    | Q(rfq__business__business_name__icontains=term)
    | Q(Exists(order_match))
  )


@supplier_quotation_status_list_docs
class SupplierQuotationStatusListApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]

  def get(self, request):
    qs = supplier_quotation_queryset(request.supplier)
    qs = apply_status_filter(qs, request.query_params.get("status"))
    qs = apply_search(qs, request.query_params.get("search"))
    return paginated_response(
      request, qs, SupplierQuotationStatusSerializer, "Quotations fetched."
    )
