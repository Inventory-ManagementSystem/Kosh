from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .permissions import HasBusiness
from rest_framework.views import APIView
from accounts.responses import success_response
from .models import Product, Category
from .serializers import ProductSerializer, StockAdjustmentSerializer, CategorySerializer
from .throttles import InventoryThrottle
from django.db import transaction
from rest_framework.exceptions import ValidationError

class ProductListCreateApi(APIView):
  permission_classes = [IsAuthenticated, HasBusiness]
  throttle_classes = [InventoryThrottle]
  def get(self, request):
    products = (
    Product.objects.filter(business=request.user.business).select_related(
      "category",
      "warehouse",
      )
    )
    search = request.query_params.get("search")
    if search:
      products = products.filter(name__icontains=search)

    category = request.query_params.get("category")
    if category:
      products = products.filter(category_id=category)

    warehouse = request.query_params.get("warehouse")
    if warehouse:
      products = products.filter(warehouse_id=warehouse)
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

    serializer = ProductSerializer(
      products,
      many=True,
      context={"request": request},
    )
    return success_response(
      "Product list fetched.",
      serializer.data,
    )

  def post(self, request):
    serializer = ProductSerializer(
      data=request.data,
      context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(
      business=request.user.business
    )
    return success_response(
      "Product created.",
      serializer.data,
      status=status.HTTP_201_CREATED,
    )


class ProductDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusiness]
  throttle_classes = [InventoryThrottle]
  def get_product(self, request, pk):
    return get_object_or_404(
      Product.objects.select_related(
        "category",
        "warehouse",
      ),
      pk=pk,
      business=request.user.business,
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
    product = self.get_product(request, pk)
    serializer = ProductSerializer(
      product,
      data=request.data,
      partial=partial,
      context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return success_response(
      "Product updated.",
      serializer.data,
    )

  def delete(self, request, pk):
    product = self.get_product(request, pk)
    product.delete()
    return success_response(
      "Product deleted.",
    )


class ProductAdjustStockApi(APIView):
  permission_classes = [IsAuthenticated, HasBusiness]
  throttle_classes = [InventoryThrottle]
  def post(self, request, pk):
    input_serializer = StockAdjustmentSerializer(
      data=request.data
    )
    input_serializer.is_valid(
      raise_exception=True
    )
    change = input_serializer.validated_data[
      "change"
    ]

    with transaction.atomic():
      product = get_object_or_404(
        Product.objects.select_for_update(),
        pk=pk,
        business=request.user.business,
      )
      new_quantity = (product.quantity + change)
      if new_quantity < 0:
        raise ValidationError({
          "change": "Insufficient stock."
        })

      product.quantity = new_quantity
      product.save(
        update_fields=[
          "quantity",
          "updated_at",
        ]
      )

    serializer = ProductSerializer(
      product,
      context={"request": request},
    )
    return success_response(
      "Stock updated.",
      serializer.data,
    )


class CategoryListCreateApi(APIView):
  permission_classes = [IsAuthenticated, HasBusiness]
  throttle_classes = [InventoryThrottle]

  def get(self, request):
    categories = Category.objects.filter(
      business=request.user.business
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
      business=request.user.business
    )
    return success_response(
      "Category created.",
      serializer.data,
      status=201,
    )


class CategoryDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusiness]
  throttle_classes = [InventoryThrottle]

  def get_category(self, request, pk):
    category = get_object_or_404(
      Category,
      pk=pk,
      business=request.user.business,
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