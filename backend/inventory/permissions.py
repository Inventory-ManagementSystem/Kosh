from rest_framework.permissions import BasePermission

class HasBusiness(BasePermission):
  message = "Register your business before using inventory."
  def has_permission(self, request, view):
    user = request.user
    return bool(
      user and user.is_authenticated and hasattr(user, "business")
    )
