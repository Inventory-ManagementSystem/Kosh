from datetime import timedelta
from django.utils import timezone

from .models import Business, Employee, EmployeeInvite
from suppliers.models import SupplierProfile
INVITE_TTL = timedelta(days=14)


def get_role(user):
    if Business.objects.filter(owner=user).exists():
        return "owner"
    if Employee.objects.filter(user=user, is_active=True).exists():
        return "employee"
    if SupplierProfile.objects.filter(user=user).exists():
        return "supplier"
    return None


def get_owned_business(user):
    return Business.objects.filter(owner=user).first()

def get_user_business(user):
    business = Business.objects.filter(owner=user).first()
    if business:
        return business

    employment = (
        Employee.objects.filter(user=user, is_active=True)
        .select_related("business")
        .first()
    )
    return employment.business if employment else None

def invite_cutoff():
    return timezone.now() - INVITE_TTL


def purge_expired_invites(business):
    EmployeeInvite.objects.filter(
        business=business, created_at__lt=invite_cutoff()
    ).delete()

def get_onboarding_state(user):
    role = get_role(user)
    selected_role = getattr(getattr(user, "profile", None), "selected_role", None)

    if role == "owner":
        next_step = "owner_dashboard"
    elif role == "employee":
        next_step = "employee_dashboard"
    elif role == "supplier":
        next_step = "supplier_dashboard"
    elif selected_role == "owner":
        next_step = "setup_business"
    elif selected_role == "employee":
        next_step = "employee_invites"
    elif selected_role == "supplier":
        next_step = "setup_supplier"
    else:
        next_step = "select_role"

    return {
        "role": role,
        "selected_role": selected_role,
        "has_business": role == "owner",
        "next_step": next_step,
        "can_change_role": role is None,
    }