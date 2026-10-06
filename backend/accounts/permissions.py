from rest_framework.permissions import BasePermission
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
