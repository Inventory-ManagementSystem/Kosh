from django.shortcuts import render

# Create your views here.

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
