"""Simple authz helpers for tenant + role checks."""

from __future__ import annotations

from functools import wraps
from typing import Callable

from django.http import JsonResponse

from .models import TenantUser

ROLE_RANK = {'readonly': 1, 'staff': 2, 'owner': 3}

ROLE_ALIAS = {
    TenantUser.Role.TENANT_USER: 'readonly',
    TenantUser.Role.TENANT_ADMIN: 'staff',
    TenantUser.Role.OWNER_ADMIN: 'owner',
    'readonly': 'readonly',
    'staff': 'staff',
    'owner': 'owner',
}


def _rank(role: str | None) -> int:
    if role is None:
        return 0
    alias = ROLE_ALIAS.get(role, str(role).lower())
    return ROLE_RANK.get(alias, 0)


def require_tenant(view_func: Callable):
    """Decorator: require request.tenant to be present."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if getattr(request, 'tenant', None) is None:
            return JsonResponse({'detail': 'tenant required'}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


def require_role(min_role: str):
    """Decorator: require minimum role (owner > staff > readonly)."""
    min_rank = ROLE_RANK.get(min_role, 0)

    def decorator(view_func: Callable):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            tenant = getattr(request, 'tenant', None)
            if tenant is None:
                return JsonResponse({'detail': 'tenant required'}, status=403)

            tenant_user = getattr(request, 'tenant_user', None)
            role = getattr(tenant_user, 'role', None)
            if _rank(role) < min_rank:
                return JsonResponse({'detail': 'insufficient role'}, status=403)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
