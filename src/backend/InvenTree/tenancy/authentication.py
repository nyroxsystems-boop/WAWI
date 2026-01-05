"""Authentication classes for tenant JWTs and service tokens."""

import logging

from django.contrib.auth.models import AnonymousUser
from rest_framework import authentication, exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication

from tenancy.context import set_current_tenant
from tenancy.models import ServiceToken, Tenant, TenantDevice

logger = logging.getLogger('inventree')


class ServiceTokenUser(AnonymousUser):
    """Pseudo user used for service token authenticated requests."""

    @property
    def is_authenticated(self):
        """Service tokens are treated as authenticated."""
        return True

    def __str__(self):
        """Readable representation."""
        return getattr(self, 'username', 'service-token')


class TenantJWTAuthentication(JWTAuthentication):
    """JWT authentication that attaches tenant context."""

    def authenticate(self, request):
        """Authenticate and set request.tenant from token claims."""
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result
        self._attach_tenant(request, validated_token)

        return (user, validated_token)

    def _attach_tenant(self, request, validated_token):
        """Set tenant and role from the token claims."""
        tenant_id = validated_token.get('tenant_id')
        if tenant_id is None:
            return

        tenant = Tenant.objects.filter(id=tenant_id).first()
        if tenant is None:
            logger.warning('JWT referenced unknown tenant_id=%s', tenant_id)
            return

        request.tenant = tenant
        request.tenant_role = validated_token.get('role')
        
        # Verify device is still active if device_id is present
        device_id = validated_token.get('device_id')
        if device_id:
            user = getattr(request, 'user', None)
            if user and not TenantDevice.objects.filter(user=user, tenant=tenant, device_id=device_id).exists():
                raise exceptions.AuthenticationFailed('Device session has been invalidated or expired')

        set_current_tenant(tenant)


class ServiceTokenAuthentication(authentication.BaseAuthentication):
    """Authenticate requests using a service token."""

    keyword = 'bearer'

    def authenticate(self, request):
        """Authenticate with a service token prefixed value."""
        auth = authentication.get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword.encode():
            return None

        try:
            raw_token = auth[1].decode()
        except IndexError:
            return None

        if not raw_token.startswith(ServiceToken.TOKEN_PREFIX):
            return None

        token = self._get_token(raw_token)
        if token is None or not token.is_active:
            raise exceptions.AuthenticationFailed('Invalid service token')

        user = ServiceTokenUser()
        user.username = f'service:{token.name}'

        request.service_token = token
        request.service = token
        if token.tenant:
            request.tenant = token.tenant
            request.tenant_role = 'SERVICE'
            set_current_tenant(token.tenant)

        token.mark_used()
        return (user, token)

    def _get_token(self, raw_token):
        """Return matching service token if any."""
        token_hash = ServiceToken.hash_token(raw_token)
        return (
            ServiceToken.objects.select_related('tenant')
            .filter(token_hash=token_hash, is_active=True)
            .first()
        )
