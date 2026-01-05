"""Models for tenancy."""

import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import TenantManager
from .context import get_current_tenant


# from django_tenants.models import TenantMixin, DomainMixin  # Removed

class Tenant(models.Model):
    """Tenant container - simplified without django-tenants."""

    # Field from TenantMixin (manually added)
    schema_name = models.CharField(max_length=63, unique=True, db_index=True)
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    status = models.CharField(max_length=20, default='active')
    is_active = models.BooleanField(default=True)
    max_users = models.IntegerField(default=5, help_text=_('Maximum number of users allowed for this tenant'))
    max_devices = models.IntegerField(default=10, help_text=_('Maximum number of concurrent devices/sessions allowed for this tenant'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Model metadata."""

        verbose_name = _('Tenant')
        verbose_name_plural = _('Tenants')

    def __str__(self):
        """Readable name."""
        return self.name

class Domain(models.Model):
    """Domain model - simplified without django-tenants."""
    
    domain = models.CharField(max_length=253, unique=True, db_index=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='domains')
    is_primary = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = _('Domain')
        verbose_name_plural = _('Domains')
    
    def __str__(self):
        return self.domain


class TenantUser(models.Model):
    """Links a user to a tenant with a specific role."""

    class Role(models.TextChoices):
        """Tenant roles."""

        OWNER_ADMIN = 'OWNER_ADMIN', 'OWNER_ADMIN'
        TENANT_ADMIN = 'TENANT_ADMIN', 'TENANT_ADMIN'
        TENANT_USER = 'TENANT_USER', 'TENANT_USER'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tenant_memberships',
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='memberships', db_index=True
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        """Model metadata."""

        unique_together = ('user', 'tenant')
        verbose_name = _('Tenant User')
        verbose_name_plural = _('Tenant Users')

    def __str__(self):
        """Readable representation."""
        return f'{self.user} @ {self.tenant} ({self.role})'


class TenantScopedModel(models.Model):
    """Abstract base for tenant-scoped entities."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True, null=True, blank=True)

    # Automatically tenant-filtered queryset
    objects = TenantManager()

    class Meta:
        """Meta options."""

        abstract = True

    def clean(self):
        """Validate tenant is set."""
        super().clean()
        if self.tenant_id is None:
            tenant = get_current_tenant()
            if tenant is not None:
                self.tenant = tenant
            else:
                raise ValidationError({'tenant': _('Tenant must be set')})

    def save(self, *args, **kwargs):
        """Ensure tenant is set before saving."""
        if self.tenant_id is None:
            tenant = get_current_tenant()
            if tenant is not None:
                self.tenant = tenant
        super().save(*args, **kwargs)


class ServiceToken(models.Model):
    """Machine-to-machine access token."""

    TOKEN_PREFIX = 'svc_'

    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=128, unique=True, db_index=True)
    scopes = models.JSONField(default=list, help_text=_('List of scopes for this token'))
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='service_tokens',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Model metadata."""

        verbose_name = _('Service Token')
        verbose_name_plural = _('Service Tokens')

    def __str__(self):
        """Readable representation."""
        return f'{self.name} ({self.tenant or "global"})'

    @staticmethod
    def hash_token(raw: str) -> str:
        """Return a secure hash for a raw token string."""
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    @classmethod
    def generate_token(cls) -> str:
        """Generate a random service token string."""
        return f'{cls.TOKEN_PREFIX}{secrets.token_urlsafe(32)}'

    def set_token(self, raw: str) -> None:
        """Set the hashed value for a raw token."""
        self.token_hash = self.hash_token(raw)

    def matches(self, raw: str) -> bool:
        """Check if the provided raw token matches this token."""
        return self.token_hash == self.hash_token(raw)

    def mark_used(self) -> None:
        """Update last usage timestamp."""
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])

    def has_scope(self, scope: str) -> bool:
        """Check if token has the given scope."""
        if not scope:
            return True
        return scope in (self.scopes or []) or '*' in (self.scopes or [])


class TenantDevice(models.Model):
    """Tracks active sessions/devices for a tenant user."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='active_devices')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='active_devices')
    device_id = models.CharField(max_length=255, db_index=True)
    last_seen = models.DateTimeField(auto_now=True)
    user_agent = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        unique_together = ('user', 'tenant', 'device_id')
        verbose_name = _('Tenant Device')
        verbose_name_plural = _('Tenant Devices')

    def __str__(self):
        return f'{self.user.username} - {self.device_id}'
