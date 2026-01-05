"""Utility helpers for tenancy."""

from typing import Optional

from .models import Tenant, TenantUser


def get_tenant_membership(request, tenant: Optional[Tenant] = None) -> Optional[TenantUser]:
    """Return the active membership for the request / tenant."""
    tenant = tenant or getattr(request, 'tenant', None)
    user = getattr(request, 'user', None)

    if tenant is None or user is None or not user.is_authenticated:
        return None

    cache_key = '_tenant_membership_cache'
    cached = getattr(request, cache_key, None)
    if cached and cached.tenant_id == tenant.id and cached.user_id == user.id:
        return cached if cached.is_active else None

    membership = TenantUser.objects.filter(
        tenant=tenant, user=user, is_active=True
    ).first()
    setattr(request, cache_key, membership)

    return membership


def get_tenant_for_user(user, tenant_id: Optional[int]) -> Optional[TenantUser]:
    """Fetch membership for a specific tenant id."""
    if tenant_id is None or user is None or not user.is_authenticated:
        return None

    return TenantUser.objects.filter(
        tenant_id=tenant_id, user=user, is_active=True
    ).first()
