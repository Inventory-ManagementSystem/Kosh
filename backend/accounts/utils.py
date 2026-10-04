from datetime import timedelta
from django.utils import timezone

from .models import Business, Employee, EmployeeInvite

INVITE_TTL = timedelta(days=14)


def get_role(user):
    if Business.objects.filter(owner=user).exists():
        return "owner"
    if Employee.objects.filter(user=user, is_active=True).exists():
        return "employee"
    return None


def get_owned_business(user):
    return Business.objects.filter(owner=user).first()


def invite_cutoff():
    return timezone.now() - INVITE_TTL


def purge_expired_invites(business):
    EmployeeInvite.objects.filter(
        business=business, created_at__lt=invite_cutoff()
    ).delete()
