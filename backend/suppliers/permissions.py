from rest_framework.permissions import BasePermission
from .models import SupplierProfile


class IsSupplier(BasePermission):
  message = "Register as a supplier before using this feature."

  def has_permission(self, request, view):
    user = request.user
    if not (user and user.is_authenticated):
      return False

    profile = SupplierProfile.objects.filter(user=user).first()
    if profile is None:
      return False

    request.supplier = profile
    return True


class IsVerifiedSupplier(BasePermission):
  message = "Register as a supplier before using this feature."

  def has_permission(self, request, view):
    if not IsSupplier().has_permission(request, view):
      self.message = "Register as a supplier before using this feature."
      return False
    if not request.supplier.is_verified:
      self.message = "Your supplier account is waiting for admin verification."
      return False
    return True
