"""Permissions for tenant-aware APIs."""

from rest_framework.permissions import BasePermission

from .models import TenantUser
from .utils import get_tenant_membership


class IsTenantMember(BasePermission):
    """Require the user to be an active member of the current tenant."""

    message = 'User is not a member of this tenant'

    def has_permission(self, request, view):
        membership = get_tenant_membership(request)
        return membership is not None


class IsOwner(BasePermission):
    """Owner-only access."""

    message = 'Owner role required'

    def has_permission(self, request, view):
        membership = get_tenant_membership(request)
        if getattr(request, 'user', None) and getattr(request.user, 'is_superuser', False):
            return True

        if membership is None:
            return False

        return membership.role == TenantUser.Role.OWNER_ADMIN


class IsServiceToken(BasePermission):
    """Require authentication via service token."""

    message = 'Valid service token required'

    def has_permission(self, request, view):
        return getattr(request, 'service_token', None) is not None


class IsTenantOrServiceToken(BasePermission):
    """Allow either tenant membership or service token."""

    message = 'Tenant membership or service token required'

    def has_permission(self, request, view):
        if getattr(request, 'service_token', None):
            return True

        return get_tenant_membership(request) is not None
