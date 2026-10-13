from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from accounts.models import Business, Employee, EmployeeInvite
from accounts.responses import error_response, success_response, validation_error_response
from accounts.swagger import UNAUTHORIZED_RESPONSE, THROTTLED_EXAMPLE, err_example, ok_example, resp
from .models import SupplierProfile, SupplyCategory, Supplier
from accounts.permissions import HasBusinessAccess, IsOwnerOrReadOnly
from .permissions import IsSupplier
from .serializers import SupplierProfileSerializer, SupplyCategorySerializer, OwnerSupplierSerializer
from .throttles import SupplierRegistrationThrottle, OwnerSupplierThrottle

from .SwaggerDocs import owner_supplier_list_create_docs, owner_supplier_detail_docs

import logging
logger = logging.getLogger(__name__)
from django.conf import settings
from django.core.mail import send_mail

SUPPLIER_EXAMPLE = {
  "id": "3f0c2a1e-8b7d-4c5e-9a10-2b3c4d5e6f70",
  "company_name": "Sharma Traders",
  "email": "orders@sharmatraders.in",
  "phone": "9876543210",
  "gstin": "07AABCS1429B1Z5",
  "address": "Shop 14, Naya Bazar",
  "city": "Delhi",
  "pincode": "110006",
  "categories": [1, 4],
  "category_names": ["Beverages", "Groceries and FMCG"],
  "is_verified": False,
  "verified_at": None,
  "created_at": "2026-10-09T10:00:00Z",
  "updated_at": "2026-10-09T10:00:00Z",
}

SUPPLIER_WRITE_EXAMPLE = {
  "company_name": "Sharma Traders",
  "phone": "9876543210",
  "gstin": "07AABCS1429B1Z5",
  "address": "Shop 14, Naya Bazar",
  "city": "Delhi",
  "pincode": "110006",
  "categories": [1, 4],
}

NOT_SUPPLIER_RESPONSE = resp(
  "The user has no supplier profile.",
  err_example(
    "Not Supplier",
    "Register as a supplier before using this feature.",
    "FORBIDDEN",
  ),
)


@extend_schema(
  summary="List Supply Categories",
  description=(
    "The shared category list a supplier picks from during registration. "
    "Managed by the admin. Any logged-in user can read it."
  ),
  responses={
    200: resp("Supply categories.",
              ok_example("Categories", "Supply categories fetched.",
                         data=[{"id": 1, "name": "Beverages"},
                               {"id": 4, "name": "Groceries and FMCG"}])),
    401: UNAUTHORIZED_RESPONSE,
  },
)
class SupplyCategoryListApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [UserRateThrottle]

  def get(self, request):
    categories = SupplyCategory.objects.filter(is_active=True)
    serializer = SupplyCategorySerializer(categories, many=True)
    return success_response("Supply categories fetched.", serializer.data)


@extend_schema(
  summary="Register as Supplier",
  description=(
    "Onboarding for the supplier role, the supplier version of Register Business. "
    "The user must already have an account (normal register, OTP or Google/GitHub "
    "login) and no role yet. The profile starts unverified until an admin approves "
    "it. `gstin` is required: a valid 15-character GSTIN that no other supplier "
    "uses. `categories` are ids from List Supply Categories."
  ),
  request=SupplierProfileSerializer,
  examples=[
    OpenApiExample("Register Supplier", value=SUPPLIER_WRITE_EXAMPLE, request_only=True),
  ],
  responses={
    201: resp("Supplier profile created, waiting for verification.",
              ok_example("Registered",
                         "Supplier registration submitted. An admin will verify your account.",
                         data=SUPPLIER_EXAMPLE)),
    400: resp("Validation error.",
              err_example("Missing GSTIN", "Validation failed.", "VALIDATION_ERROR",
                          errors={"gstin": ["This field is required."]}),
              err_example("Invalid GSTIN", "Validation failed.", "VALIDATION_ERROR",
                          errors={"gstin": ["Enter a valid 15-character GSTIN."]}),
              err_example("Duplicate GSTIN", "Validation failed.", "VALIDATION_ERROR",
                          errors={"gstin": ["This GSTIN is already registered to another supplier."]}),
              err_example("Other Fields", "Validation failed.", "VALIDATION_ERROR",
                          errors={"pincode": ["Enter a valid 6-digit pincode."],
                                  "categories": ["This list may not be empty."]})),
    401: UNAUTHORIZED_RESPONSE,
    409: resp("The user already has a role, or the GSTIN was taken at the same moment.",
              err_example("Is Owner", "Business owners cannot register as a supplier.",
                          "OWNER_CANNOT_REGISTER_SUPPLIER"),
              err_example("Is Employee", "Employees cannot register as a supplier.",
                          "EMPLOYEE_CANNOT_REGISTER_SUPPLIER"),
              err_example("Already Supplier", "You are already registered as a supplier.",
                          "ALREADY_SUPPLIER"),
              err_example("GSTIN Exists", "This GSTIN is already registered to another supplier.",
                          "GSTIN_EXISTS")),
    429: resp("Too many requests.", THROTTLED_EXAMPLE),
  },
)
class SupplierRegistrationApi(APIView):
  permission_classes = [IsAuthenticated]
  throttle_classes = [SupplierRegistrationThrottle]

  def post(self, request):
    user = request.user
    if Business.objects.filter(owner=user).exists():
      return error_response(
        "Business owners cannot register as a supplier.", "OWNER_CANNOT_REGISTER_SUPPLIER",
        status=status.HTTP_409_CONFLICT,
      )
    if Employee.objects.filter(user=user).exists():
      return error_response(
        "Employees cannot register as a supplier.", "EMPLOYEE_CANNOT_REGISTER_SUPPLIER",
        status=status.HTTP_409_CONFLICT,
      )
    if SupplierProfile.objects.filter(user=user).exists():
      return error_response(
        "You are already registered as a supplier.", "ALREADY_SUPPLIER",
        status=status.HTTP_409_CONFLICT,
      )

    serializer = SupplierProfileSerializer(data=request.data)
    if not serializer.is_valid():
      return validation_error_response(serializer)

    try:
      with transaction.atomic():
        profile = serializer.save(user=user)
        Supplier.objects.filter(
          email__iexact=user.email, linked_account__isnull=True
        ).update(linked_account=profile)
    except IntegrityError:
      if SupplierProfile.objects.filter(user=user).exists():
        return error_response(
          "You are already registered as a supplier.", "ALREADY_SUPPLIER",
          status=status.HTTP_409_CONFLICT,
        )
      return error_response(
        "This GSTIN is already registered to another supplier.", "GSTIN_EXISTS",
        status=status.HTTP_409_CONFLICT,
      )

    EmployeeInvite.objects.filter(email__iexact=user.email).delete()

    return success_response(
      "Supplier registration submitted. An admin will verify your account.",
      SupplierProfileSerializer(profile).data,
      status=status.HTTP_201_CREATED,
    )


class MySupplierProfileApi(APIView):
  permission_classes = [IsAuthenticated, IsSupplier]
  throttle_classes = [UserRateThrottle]

  @extend_schema(
    summary="Get My Supplier Profile",
    description=(
      "The logged-in supplier's profile, including `is_verified`. Works before "
      "verification too, so the app can show a 'waiting for approval' screen."
    ),
    responses={
      200: resp("Supplier profile.",
                ok_example("Profile", "Supplier profile fetched.", data=SUPPLIER_EXAMPLE)),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
    },
  )
  def get(self, request):
    serializer = SupplierProfileSerializer(request.supplier)
    return success_response("Supplier profile fetched.", serializer.data)

  @extend_schema(
    summary="Update My Supplier Profile",
    description=(
      "Partial update. Send only the fields you want to change. Changing "
      "`company_name` or `gstin` on a verified profile sends it back to "
      "unverified until an admin checks it again."
    ),
    request=SupplierProfileSerializer,
    examples=[
      OpenApiExample("Change Phone", value={"phone": "9123456780"}, request_only=True),
      OpenApiExample("Change Categories", value={"categories": [1, 2, 4]}, request_only=True),
    ],
    responses={
      200: resp("Supplier profile updated.",
                ok_example("Updated", "Supplier profile updated.", data=SUPPLIER_EXAMPLE)),
      400: resp("Validation error.",
                err_example("Validation Error", "Validation failed.", "VALIDATION_ERROR",
                            errors={"gstin": ["Enter a valid 15-character GSTIN."]})),
      401: UNAUTHORIZED_RESPONSE,
      403: NOT_SUPPLIER_RESPONSE,
      409: resp("GSTIN taken.",
                err_example("GSTIN Exists", "This GSTIN is already registered to another supplier.",
                            "GSTIN_EXISTS")),
    },
  )
  def patch(self, request):
    serializer = SupplierProfileSerializer(
      request.supplier,
      data=request.data,
      partial=True,
    )
    if not serializer.is_valid():
      return validation_error_response(serializer)

    try:
      with transaction.atomic():
        serializer.save()
    except IntegrityError:
      return error_response(
        "This GSTIN is already registered to another supplier.", "GSTIN_EXISTS",
        status=status.HTTP_409_CONFLICT,
      )

    return success_response("Supplier profile updated.", serializer.data)

@owner_supplier_list_create_docs
class OwnerSupplierListCreateApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess, IsOwnerOrReadOnly]
  throttle_classes = [OwnerSupplierThrottle]

  def get(self, request):
    suppliers = (
      Supplier.objects.filter(business=request.business)
      .select_related("linked_account")
      .prefetch_related("linked_account__categories")
    )
    search = request.query_params.get("search")
    if search:
      suppliers = suppliers.filter(
        Q(email__icontains=search)
        | Q(label__icontains=search)
        | Q(linked_account__company_name__icontains=search)
      )
    is_active = request.query_params.get("is_active")
    if is_active in ("true", "false"):
      suppliers = suppliers.filter(is_active=(is_active == "true"))
    serializer = OwnerSupplierSerializer(suppliers, many=True, context={"request": request})
    return success_response("Supplier list fetched.", serializer.data)

  def post(self, request):
    serializer = OwnerSupplierSerializer(data=request.data, context={"request": request})
    if not serializer.is_valid():
      return validation_error_response(serializer)
    try:
      with transaction.atomic():
        supplier = serializer.save(business=request.business)
    except IntegrityError:
      return error_response(
        "This supplier is already in your list.", "SUPPLIER_EXISTS",
        status=status.HTTP_409_CONFLICT,
      )

    if supplier.linked_account_id is None:
      try:
        send_mail(
          f"{request.business.business_name} has invited you to supply on Kosh",
          (
            f"{request.business.business_name} wants to send you requests for "
            "quotation on Kosh.\n\n"
            f"Sign up or log in with this email address ({supplier.email}), "
            "choose the Supplier option, and register your agency:\n"
            f"{settings.FRONTEND_URL}/role"
          ),
          None,
          [supplier.email],
        )
      except Exception:
        logger.exception("Supplier invite email failed")

    return success_response("Supplier created.", serializer.data, status=status.HTTP_201_CREATED)

@owner_supplier_detail_docs
class OwnerSupplierDetailApi(APIView):
  permission_classes = [IsAuthenticated, HasBusinessAccess, IsOwnerOrReadOnly]
  throttle_classes = [OwnerSupplierThrottle]

  def get_supplier(self, request, pk):
    return get_object_or_404(Supplier.objects.select_related("linked_account"), pk=pk, business=request.business)

  def get(self, request, pk):
    serializer = OwnerSupplierSerializer(
      self.get_supplier(request, pk), context={"request": request}
    )
    return success_response("Supplier fetched.", serializer.data)

  def patch(self, request, pk):
    serializer = OwnerSupplierSerializer(
      self.get_supplier(request, pk), data=request.data, partial=True,
      context={"request": request},
    )
    if not serializer.is_valid():
      return validation_error_response(serializer)
    try:
      with transaction.atomic():
        serializer.save()
    except IntegrityError:
      return error_response(
        "A supplier with this email already exists.", "SUPPLIER_EXISTS",
        status=status.HTTP_409_CONFLICT,
      )
    return success_response("Supplier updated.", serializer.data)

  def delete(self, request, pk):
    supplier = self.get_supplier(request, pk)
    try:
      supplier.delete()
    except ProtectedError:
      return error_response(
        "This supplier has RFQ history. Set is_active to false instead.",
        "SUPPLIER_HAS_HISTORY",
        status=status.HTTP_409_CONFLICT,
      )
    return success_response("Supplier deleted.")
