from rest_framework.permissions import BasePermission, SAFE_METHODS
from .utils import get_user_business


class HasBusinessAccess(BasePermission):
  message = "Register your business or join one before using this feature."

  def has_permission(self, request, view):
    user = request.user
    if not (user and user.is_authenticated):
      return False

    business = get_user_business(user)
    if business is None:
      return False

    request.business = business
    return True


class IsOwner(BasePermission):
  message = "Only the business owner can perform this action."

  def has_permission(self, request, view):
    business = getattr(request, "business", None)
    return business is not None and business.owner_id == request.user.id


class IsOwnerOrReadOnly(IsOwner):
  def has_permission(self, request, view):
    if request.method in SAFE_METHODS:
      return True
    return super().has_permission(request, view)