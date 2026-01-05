"""Audit helpers."""

from typing import Any, Optional

from django.contrib.auth import get_user_model

from audit.models import AuditLog
from tenancy.models import Tenant


def log_audit(action: str, *, tenant: Optional[Tenant] = None, actor=None, metadata: Optional[dict] = None):
    """Create an audit log entry."""
    AuditLog.objects.create(
        tenant=tenant,
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        metadata=metadata or {},
    )
