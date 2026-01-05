"""Utilities for tracking the current tenant in the request cycle."""

from contextvars import ContextVar
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .models import Tenant  # noqa: F401

_current_tenant: ContextVar[Optional['Tenant']] = ContextVar(
    'current_tenant', default=None
)


def set_current_tenant(tenant: Optional['Tenant']) -> None:
    """Persist the current tenant for the running context."""
    _current_tenant.set(tenant)


def get_current_tenant() -> Optional['Tenant']:
    """Return the tenant stored for the running context, if any."""
    return _current_tenant.get()


def clear_current_tenant() -> None:
    """Reset the stored tenant."""
    _current_tenant.set(None)
