from rest_framework.permissions import BasePermission
from accounts.permissions import HasBusinessAccess
from suppliers.permissions import IsSupplier


class HasAssistantAccess(BasePermission):
  message = "Register your business, join one or register as a supplier before using the assistant."
  def has_permission(self, request, view):
    request.business = None
    request.supplier = None
    if HasBusinessAccess().has_permission(request, view):
      return True
    return IsSupplier().has_permission(request, view)