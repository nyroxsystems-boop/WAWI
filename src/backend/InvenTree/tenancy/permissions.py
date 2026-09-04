"""Permissions for tenant-aware APIs."""

from rest_framework.permissions import BasePermission, SAFE_METHODS

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


class IsPlatformAdmin(BasePermission):
    """Require a real Django superuser for platform-wide operations."""

    message = 'Platform administrator required'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_superuser
        )


class IsActiveTenantContext(BasePermission):
    """Require current active tenant membership on default API routes.

    Platform superusers retain global administration access. Machine tokens
    must use an endpoint with an explicit IsTenantOrServiceToken permission so
    scopes are evaluated instead of inheriting generic authenticated access.
    """

    message = 'Active tenant context required'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and user.is_superuser:
            return True
        if getattr(request, 'service_token', None) is not None:
            return False
        tenant = getattr(request, 'tenant', None)
        if tenant is None or not tenant.is_active or tenant.status != 'active':
            return False
        return get_tenant_membership(request, tenant=tenant) is not None


class IsServiceToken(BasePermission):
    """Require authentication via service token."""

    message = 'Valid service token required'

    def has_permission(self, request, view):
        return getattr(request, 'service_token', None) is not None


class IsTenantOrServiceToken(BasePermission):
    """Authorize tenant users and narrowly scoped machine tokens.

    Human users require an active membership. Read-only members may only use
    safe methods; tenant administrators and owners may mutate tenant data.
    Service tokens are never treated as equivalent to a human owner: every
    view must declare an explicit scope or fall into a known, least-privilege
    module scope.
    """

    message = 'Tenant membership or service token required'

    _MODULE_SCOPES = {
        'billing': 'billing',
        'channels': 'channels',
        'extsync': 'extsync',
        'outbox': 'outbox',
        'wws': 'wws',
    }

    def has_permission(self, request, view):
        service_token = getattr(request, 'service_token', None)
        if service_token is not None:
            required_scope = self._required_service_scope(request, view)
            if not required_scope:
                self.message = 'This endpoint does not permit service-token access'
                return False
            if not service_token.has_scope(required_scope):
                self.message = f'Service token requires scope: {required_scope}'
                return False
            return True

        membership = get_tenant_membership(request)
        if membership is None:
            return False

        allowed_read_roles = getattr(
            view,
            'tenant_read_roles',
            {
                TenantUser.Role.TENANT_USER,
                TenantUser.Role.TENANT_ADMIN,
                TenantUser.Role.OWNER_ADMIN,
            },
        )
        allowed_write_roles = getattr(
            view,
            'tenant_write_roles',
            {TenantUser.Role.TENANT_ADMIN, TenantUser.Role.OWNER_ADMIN},
        )

        allowed_roles = (
            allowed_read_roles if request.method in SAFE_METHODS else allowed_write_roles
        )
        if membership.role not in allowed_roles:
            self.message = 'Insufficient tenant role for this action'
            return False

        return True

    def _required_service_scope(self, request, view):
        """Return the exact scope required for this view and HTTP method."""
        declared = getattr(view, 'required_service_scopes', None)
        if isinstance(declared, dict):
            return declared.get(request.method)

        declared = getattr(view, 'required_service_scope', None)
        if declared:
            return declared

        module_root = view.__class__.__module__.split('.', 1)[0]
        namespace = self._MODULE_SCOPES.get(module_root)
        if not namespace:
            return None

        action = 'read' if request.method in SAFE_METHODS else 'write'
        return f'{namespace}.{action}'
