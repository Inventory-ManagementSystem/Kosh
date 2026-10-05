
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from accounts.permissions import HasBusinessAccess
from accounts.responses import success_response, validation_error_response
from inventory.throttles import InventoryThrottle

from .models import Customer
from .serializers import CustomerSerializer

from drf_spectacular.utils import (
  extend_schema,
  extend_schema_view,
  OpenApiExample,
  OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

from accounts.swagger import (
  ok_example,
  err_example,
  resp,
  THROTTLED_EXAMPLE,
  UNAUTHORIZED_RESPONSE,
)

CUSTOMER_EXAMPLE = {
  "id": "3f2b8c1e-6d4a-4c1b-9a57-2e8f0b7d1a42",
  "name": "Ravi Kumar",
  "email": "ravi@example.com",
  "phone": "9876543210",
  "address": "12 MG Road, Ghaziabad",
  "is_active": True,
  "created_at": "2026-10-05T10:00:00Z",
  "updated_at": "2026-10-05T10:00:00Z",
}

FORBIDDEN_RESPONSE = resp(
  "User has no business (neither owner nor active employee).",
  err_example(
    "No Business",
    "Register your business or join one before using this feature.",
    "FORBIDDEN",
  ),
)

NOT_FOUND_RESPONSE = resp(
  "No such customer in this business.",
  err_example("Not Found", "No Customer matches the given query.", "NOT_FOUND"),
)

VALIDATION_RESPONSE = resp(
  "Validation error.",
  err_example(
    "Validation Error",
    "Validation failed.",
    "VALIDATION_ERROR",
    errors={"phone": ["Enter a valid phone number."]},
  ),
)

@extend_schema_view(
  get=extend_schema(
    summary="List Customers",
    description=(
      "Returns all customers of the logged-in user's business. Works for both "
      "owners and employees. Optionally filter with `search` and `is_active`."
    ),
    parameters=[
      OpenApiParameter(
        "search", OpenApiTypes.STR, OpenApiParameter.QUERY,
        description="Matches part of the name, email or phone.",
      ),
      OpenApiParameter(
        "is_active", OpenApiTypes.STR, OpenApiParameter.QUERY,
        enum=["true", "false"],
        description="Show only active or only inactive customers.",
      ),
    ],
    responses={
      200: resp("Customer list.",
                ok_example("Customers", "Customer list fetched.",
                           data=[CUSTOMER_EXAMPLE])),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
    },
  ),
  post=extend_schema(
    summary="Create Customer",
    description=(
      "Creates a customer in the logged-in user's business. The business is set "
      "by the server, never by the request body."
    ),
    request=CustomerSerializer,
    examples=[
      OpenApiExample(
        "Create Customer",
        value={
          "name": "Ravi Kumar",
          "email": "Ravi@Example.com",
          "phone": "9876543210",
          "address": "12 MG Road, Ghaziabad",
        },
        request_only=True,
      ),
      OpenApiExample(
        "Name Only (walk-in customer)",
        value={"name": "Walk-in Customer"},
        request_only=True,
      ),
    ],
    responses={
      201: resp("Customer created.",
                ok_example("Created", "Customer created.", data=CUSTOMER_EXAMPLE)),
      400: VALIDATION_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      429: resp("Too many write requests.", THROTTLED_EXAMPLE),
    },
  ),
)

class CustomerListCreateApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]
  throttle_classes = [InventoryThrottle]

  def get(self, request):
    customers = Customer.objects.filter(business=request.business)

    search = request.query_params.get("search")
    if search:
      customers = customers.filter(
        Q(name__icontains=search)
        | Q(email__icontains=search)
        | Q(phone__icontains=search)
      )

    is_active = request.query_params.get("is_active")
    if is_active in ("true", "false"):
      customers = customers.filter(is_active=(is_active == "true"))

    serializer = CustomerSerializer(customers, many=True)
    return success_response("Customer list fetched.", serializer.data)

  def post(self, request):
    serializer = CustomerSerializer(data=request.data)
    if not serializer.is_valid():
      return validation_error_response(serializer)

    serializer.save(business=request.business)
    return success_response(
      "Customer created.",
      serializer.data,
      status=status.HTTP_201_CREATED,
    )

@extend_schema_view(
  get=extend_schema(
    summary="Get Customer",
    responses={
      200: resp("Customer details.",
                ok_example("Customer", "Customer fetched.", data=CUSTOMER_EXAMPLE)),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: NOT_FOUND_RESPONSE,
    },
  ),
  put=extend_schema(
    summary="Replace Customer",
    description="Full update. `name` is required; omitted optional fields are reset.",
    request=CustomerSerializer,
    responses={
      200: resp("Customer updated.",
                ok_example("Updated", "Customer updated.", data=CUSTOMER_EXAMPLE)),
      400: VALIDATION_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: NOT_FOUND_RESPONSE,
      429: resp("Too many write requests.", THROTTLED_EXAMPLE),
    },
  ),
  patch=extend_schema(
    summary="Update Customer",
    description="Partial update. Send only the fields you want to change.",
    request=CustomerSerializer,
    examples=[
      OpenApiExample(
        "Deactivate Customer",
        value={"is_active": False},
        request_only=True,
      ),
    ],
    responses={
      200: resp("Customer updated.",
                ok_example("Updated", "Customer updated.", data=CUSTOMER_EXAMPLE)),
      400: VALIDATION_RESPONSE,
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: NOT_FOUND_RESPONSE,
      429: resp("Too many write requests.", THROTTLED_EXAMPLE),
    },
  ),
  delete=extend_schema(
    summary="Delete Customer",
    description="Permanently deletes the customer.",
    responses={
      200: resp("Customer deleted.",
                ok_example("Deleted", "Customer deleted.")),
      401: UNAUTHORIZED_RESPONSE,
      403: FORBIDDEN_RESPONSE,
      404: NOT_FOUND_RESPONSE,
      429: resp("Too many write requests.", THROTTLED_EXAMPLE),
    },
  ),
)

class CustomerDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess]
  throttle_classes = [InventoryThrottle]

  def get_customer(self, request, pk):
    return get_object_or_404(
      Customer,
      pk=pk,
      business=request.business,
    )

  def get(self, request, pk):
    customer = self.get_customer(request, pk)
    serializer = CustomerSerializer(customer)
    return success_response("Customer fetched.", serializer.data)

  def put(self, request, pk):
    return self.update(request, pk, partial=False)

  def patch(self, request, pk):
    return self.update(request, pk, partial=True)

  def update(self, request, pk, partial):
    customer = self.get_customer(request, pk)
    serializer = CustomerSerializer(customer, data=request.data, partial=partial)
    if not serializer.is_valid():
      return validation_error_response(serializer)

    serializer.save()
    return success_response("Customer updated.", serializer.data)

  def delete(self, request, pk):
    customer = self.get_customer(request, pk)
    customer.delete()
    return success_response("Customer deleted.")
