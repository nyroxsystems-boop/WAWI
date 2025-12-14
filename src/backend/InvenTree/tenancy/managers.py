"""Custom managers and querysets for tenant-aware models."""

from django.db import models

from .context import get_current_tenant


class TenantQuerySet(models.QuerySet):
    """QuerySet with helpers for tenant filtering."""

    def for_tenant(self, tenant):
        """Restrict to the given tenant."""
        if tenant is None:
            return self.none()
        return self.filter(tenant=tenant)


class TenantManager(models.Manager):
    """Manager that automatically scopes queries to the current tenant context."""

    def get_queryset(self):
        """Return queryset optionally filtered by the current tenant."""
        qs = TenantQuerySet(self.model, using=self._db)

        tenant = get_current_tenant()
        if tenant is not None:
            qs = qs.filter(tenant=tenant)

        return qs

    def for_tenant(self, tenant):
        """Shortcut to filter objects for a provided tenant."""
        return TenantQuerySet(self.model, using=self._db).for_tenant(tenant)
