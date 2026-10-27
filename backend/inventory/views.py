from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from accounts.permissions import HasBusinessAccess, IsOwnerOrReadOnly
from rest_framework.views import APIView
from accounts.responses import success_response
from .models import Product, Category, StockMovement, Outlet, DispatchNote
from .serializers import (
  ProductSerializer, StockAdjustmentSerializer, CategorySerializer,
  WarehouseSerializer, OutletSerializer, DispatchCreateSerializer, DispatchNoteSerializer,
  StockMovementSerializer,
)
from .services import get_warehouse
from .throttles import InventoryThrottle
from django.db import transaction
from django.db.models import ProtectedError, RestrictedError
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from accounts.pagination import StandardPagination

from .ledger import record_movement, create_dispatch
from procurement.alert_services import check_low_stock_on_commit, close_active_alerts

from .SwaggerDocs import (
  product_list_create_docs,
  product_detail_docs,
  product_adjust_stock_docs,
  category_list_create_docs,
  category_detail_docs,
  warehouse_docs,
  outlet_list_create_docs,
  outlet_detail_docs,
  dispatch_list_create_docs,
  dispatch_detail_docs,
  stock_movement_list_docs,
)
import uuid

REORDER_FIELDS = {"low_stock_threshold", "lead_time_days", "safety_stock", "reorder_quantity", "is_active"}

class InventoryPagination(StandardPagination):
    message = "Product list fetched."


@product_list_create_docs
class ProductListCreateApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess, IsOwnerOrReadOnly]
  throttle_classes = [InventoryThrottle]
  parser_classes = [MultiPartParser, FormParser, JSONParser]

  def validate_uuid(self, value, field_name):
    try:
      return uuid.UUID(value)
    except ValueError:
      raise ValidationError(
        f"Invalid {field_name} UUID."
      )
    
  def get(self, request):
    products = (
    Product.objects.filter(business=request.business).select_related(
      "category",
      "supply_category",
      "warehouse",
      )
    )
    is_active = request.query_params.get("is_active", "true")
    if is_active in ("true", "false"):
      products = products.filter(is_active=(is_active == "true"))
    search = request.query_params.get("search")
    if search:
      products = products.filter(name__icontains=search)

    category = request.query_params.get("category")
    if category:
      category = self.validate_uuid(category, "category")
      products = products.filter(category_id=category)

    ordering = request.query_params.get("ordering")
    if ordering:
      allowed_fields = {
        "name",
        "price",
        "created_at",
        "updated_at",
        }
      requested_fields = ordering.split(",")
      if all(field.lstrip("-") in allowed_fields for field in requested_fields):
        products = products.order_by(*requested_fields)

    paginator = InventoryPagination()
    page = paginator.paginate_queryset(products, request)
    serializer = ProductSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)

  def post(self, request):
    serializer = ProductSerializer(
      data=request.data,
      context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    opening_qty = serializer.validated_data.pop("opening_quantity", 0)

    with transaction.atomic():
      product = serializer.save(
        business=request.business,
        warehouse=get_warehouse(request.business),
      )
      if opening_qty > 0:
        record_movement(
          business=request.business,
          product_id=product.pk,
          change=opening_qty,
          reason=StockMovement.Reason.OPENING_BALANCE,
          user=request.user,
          note="Opening stock",
        )
        product.refresh_from_db(fields=["quantity"])

    return success_response(
      "Product created.",
      serializer.data,
      status=status.HTTP_201_CREATED,
    )
  

@product_detail_docs
class ProductDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess, IsOwnerOrReadOnly]
  throttle_classes = [InventoryThrottle]
  parser_classes = [MultiPartParser, FormParser, JSONParser]
  def get_product(self, request, pk):
    return get_object_or_404(
      Product.objects.select_related(
        "category",
        "supply_category",
        "warehouse",
      ),
      pk=pk,
      business=request.business,
    )

  def get(self, request, pk):
    product = self.get_product(request, pk)
    serializer = ProductSerializer(
      product,
      context={"request": request},
    )
    return success_response(
      "Product fetched.",
      serializer.data,
    )

  def put(self, request, pk):
    return self.update(
      request,
      pk,
      partial=False,
    )

  def patch(self, request, pk):
    return self.update(
      request,
      pk,
      partial=True,
    )

  def update(self, request, pk, partial):
    if "quantity" in request.data:
      raise ValidationError({"quantity": "Use the stock adjustment endpoint to change stock."})
    product = self.get_product(request, pk)
    serializer = ProductSerializer(
      product,
      data=request.data,
      partial=partial,
      context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
      serializer.save()
      changed = set(serializer.validated_data)
      if "is_active" in changed and not product.is_active:
        close_active_alerts([product.pk])
      elif "is_active" in changed or REORDER_FIELDS & changed:
        check_low_stock_on_commit(request.business, [product.pk])
    return success_response(
      "Product updated.",
      serializer.data,
    )

  def delete(self, request, pk):
    product = self.get_product(request, pk)
    try:
      with transaction.atomic():
        product.delete()
    except (ProtectedError, RestrictedError):
      with transaction.atomic():
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        close_active_alerts([product.pk])
      return success_response(
        "Product has order or dispatch history, so it was deactivated instead of deleted.",
        {"archived": True},
      )
    return success_response("Product deleted.", {"archived": False})


@product_adjust_stock_docs
class ProductAdjustStockApi(APIView):
  permission_classes = [IsAuthenticated,HasBusinessAccess,]
  throttle_classes = [InventoryThrottle]
  def post(self, request, pk):
    input_serializer = StockAdjustmentSerializer(
      data=request.data
    )
    input_serializer.is_valid(
      raise_exception=True
    )
    data = input_serializer.validated_data

    with transaction.atomic():
      movement = record_movement(
        business=request.business,
        product_id=pk,
        change=data["change"],
        reason=data["reason"],
        user=request.user,
        note=data.get("note", ""),
      )
      if data["change"] < 0:
        check_low_stock_on_commit(request.business, [pk])
    product = movement.product

    serializer = ProductSerializer(
      product,
      context={"request": request},
    )
    return success_response(
      "Stock updated.",
      serializer.data,
    )


@category_list_create_docs
class CategoryListCreateApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess, IsOwnerOrReadOnly]
  throttle_classes = [InventoryThrottle]

  def get(self, request):
    categories = Category.objects.filter(
      business=request.business
    )
    serializer = CategorySerializer(
      categories,
      many=True,
      context={"request": request},
    )
    return success_response(
      "Category list fetched.",
      serializer.data,
    )

  def post(self, request):
    serializer = CategorySerializer(
      data=request.data,
      context={"request": request},
    )
    serializer.is_valid(
      raise_exception=True
    )
    serializer.save(
      business=request.business
    )
    return success_response(
      "Category created.",
      serializer.data,
      status=201,
    )


@category_detail_docs
class CategoryDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess, IsOwnerOrReadOnly]
  throttle_classes = [InventoryThrottle]

  def get_category(self, request, pk):
    category = get_object_or_404(
      Category,
      pk=pk,
      business=request.business,
    )
    self.check_object_permissions(
      request,
      category,
    )
    return category

  def get(self, request, pk):
    category = self.get_category(
      request,
      pk,
    )
    serializer = CategorySerializer(
      category,
      context={"request": request},
    )
    return success_response(
      "Category fetched.",
      serializer.data,
    )

  def put(self, request, pk):
    return self.update(
      request,
      pk,
      partial=False,
    )
    
  def patch(self, request, pk):
    return self.update(
      request,
      pk,
      partial=True,
    )

  def update(self, request, pk, partial):
    category = self.get_category(
      request,
      pk,
    )
    serializer = CategorySerializer(
      category,
      data=request.data,
      partial=partial,
      context={"request": request},
    )
    serializer.is_valid(
      raise_exception=True
    )
    serializer.save()
    return success_response(
      "Category updated.",
      serializer.data,
    )

  def delete(self, request, pk):
    category = self.get_category(
      request,
      pk,
    )
    category.delete()
    return success_response(
      "Category deleted."
    )


@warehouse_docs
class WarehouseApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess, IsOwnerOrReadOnly]
  throttle_classes = [InventoryThrottle]

  def get(self, request):
    warehouse = get_warehouse(request.business)
    serializer = WarehouseSerializer(
      warehouse,
      context={"request": request},
    )
    return success_response(
      "Warehouse fetched.",
      serializer.data,
    )

  def put(self, request):
    return self.update(
      request,
      partial=False,
    )

  def patch(self, request):
    return self.update(
      request,
      partial=True,
    )

  def update(self, request, partial):
    warehouse = get_warehouse(request.business)
    serializer = WarehouseSerializer(
      warehouse,
      data=request.data,
      partial=partial,
      context={"request": request},
    )
    serializer.is_valid(
      raise_exception=True
    )
    serializer.save()
    return success_response(
      "Warehouse updated.",
      serializer.data,
    )

@outlet_list_create_docs
class OutletListCreateApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]
  throttle_classes = [InventoryThrottle]

  def get(self, request):
    outlets = Outlet.objects.filter(business=request.business)
    is_active = request.query_params.get("is_active")
    if is_active in ("true", "false"):
      outlets = outlets.filter(is_active=(is_active == "true"))
    serializer = OutletSerializer(outlets, many=True, context={"request": request})
    return success_response("Outlet list fetched.", serializer.data)

  def post(self, request):
    serializer = OutletSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    serializer.save(business=request.business)
    return success_response("Outlet created.", serializer.data, status=201)

@outlet_detail_docs
class OutletDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess, IsOwnerOrReadOnly]
  throttle_classes = [InventoryThrottle]

  def get_outlet(self, request, pk):
    return get_object_or_404(Outlet, pk=pk, business=request.business)

  def get(self, request, pk):
    serializer = OutletSerializer(self.get_outlet(request, pk), context={"request": request})
    return success_response("Outlet fetched.", serializer.data)

  def put(self, request, pk):
    return self.update(request, pk, partial=False)

  def patch(self, request, pk):
    return self.update(request, pk, partial=True)

  def update(self, request, pk, partial):
    serializer = OutletSerializer(
      self.get_outlet(request, pk),
      data=request.data,
      partial=partial,
      context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return success_response("Outlet updated.", serializer.data)

  def delete(self, request, pk):
    outlet = self.get_outlet(request, pk)
    try:
      outlet.delete()
    except ProtectedError:
      raise ValidationError(
        "This outlet has dispatch history. Set is_active to false instead."
      )
    return success_response("Outlet deleted.")


class DispatchPagination(StandardPagination):
  message = "Dispatch list fetched."


@dispatch_list_create_docs
class DispatchListCreateApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]
  throttle_classes = [InventoryThrottle]

  def get(self, request):
    dispatches = (
      DispatchNote.objects.filter(business=request.business)
      .select_related("outlet", "created_by")
      .prefetch_related("items__product")
    )

    outlet = request.query_params.get("outlet")
    if outlet:
      try:
        dispatches = dispatches.filter(outlet_id=uuid.UUID(outlet))
      except ValueError:
        raise ValidationError({"outlet": "Invalid outlet UUID."})

    for param, lookup in (("from", "dispatch_date__gte"), ("to", "dispatch_date__lte")):
      raw = request.query_params.get(param)
      if raw:
        try:
          value = parse_date(raw)
        except ValueError:
          value = None
        if value is None:
          raise ValidationError({param: "Use YYYY-MM-DD."})
        dispatches = dispatches.filter(**{lookup: value})

    paginator = DispatchPagination()
    page = paginator.paginate_queryset(dispatches, request)
    serializer = DispatchNoteSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)

  def post(self, request):
    serializer = DispatchCreateSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    with transaction.atomic():
      note = create_dispatch(
        business=request.business,
        outlet_id=data["outlet"].pk,
        items=[
          {"product_id": i["product"].pk, "quantity": i["quantity"]}
          for i in data["items"]
        ],
        user=request.user,
        dispatch_date=data.get("dispatch_date"),
        notes=data.get("notes", ""),
      )
      check_low_stock_on_commit(request.business, [i["product"].pk for i in data["items"]])
    return success_response(
      "Dispatch recorded.",
      DispatchNoteSerializer(note, context={"request": request}).data,
      status=status.HTTP_201_CREATED,
    )

@dispatch_detail_docs
class DispatchDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]
  throttle_classes = [InventoryThrottle]

  def get(self, request, pk):
    note = get_object_or_404(
      DispatchNote.objects.select_related("outlet", "created_by").prefetch_related("items__product"),
      pk=pk,
      business=request.business,
    )
    return success_response(
      "Dispatch fetched.",
      DispatchNoteSerializer(note, context={"request": request}).data,
    )

class StockMovementPagination(StandardPagination):
  message = "Stock movement list fetched."


@stock_movement_list_docs
class StockMovementListApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]
  throttle_classes = [InventoryThrottle]

  def get(self, request):
    movements = StockMovement.objects.filter(
      business=request.business
    ).select_related("product", "dispatch_note", "created_by")

    product = request.query_params.get("product")
    if product:
      try:
        movements = movements.filter(product_id=uuid.UUID(product))
      except ValueError:
        raise ValidationError({"product": "Invalid product UUID."})

    reason = request.query_params.get("reason")
    if reason:
      if reason not in StockMovement.Reason.values:
        raise ValidationError({"reason": "Invalid reason."})
      movements = movements.filter(reason=reason)

    for param, lookup in (("from", "created_at__date__gte"), ("to", "created_at__date__lte")):
      raw = request.query_params.get(param)
      if raw:
        try:
          value = parse_date(raw)
        except ValueError:
          value = None
        if value is None:
          raise ValidationError({param: "Use YYYY-MM-DD."})
        movements = movements.filter(**{lookup: value})

    paginator = StockMovementPagination()
    page = paginator.paginate_queryset(movements, request)
    serializer = StockMovementSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)
