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
