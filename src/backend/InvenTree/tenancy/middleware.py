"""Middleware to attach tenant context to each request."""

import logging
from typing import Optional

from django.http import Http404, HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import InvalidToken, TokenBackendError
from rest_framework_simplejwt.settings import api_settings

from .context import clear_current_tenant, set_current_tenant
from .models import ServiceToken, Tenant, TenantUser
from audit.utils import log_audit
# from django_tenants.utils import set_tenant  # Removed - not needed

logger = logging.getLogger('inventree')


class SubdomainTenantMiddleware(MiddlewareMixin):
    """Resolve tenant from subdomain: <slug>.euredomain.de -> request.tenant."""

    def process_request(self, request):
        host = (request.get_host() or '').split(':')[0]
        parts = host.split('.')

        # Not enough parts to contain a subdomain => no tenant context
        if len(parts) < 3:
            request.tenant = None
            request.tenant_id = None
            request.tenant_user = None
            logger.debug('tenant.resolve', extra={'host': host, 'slug': None, 'tenant': None})
            return None

        # Allow selected public endpoints without tenant lookup
        if request.path.startswith((
            '/api/bot/health',
            '/api/dashboard/orders',
            '/api/dashboard/offers',
            '/api/dashboard/suppliers',
            '/api/dashboard/wws-connections',
            '/api/wws-connections',
            '/api/bot/inventory/by-oem',
        )):
            request.tenant = None
            request.tenant_id = None
            request.tenant_user = None
            logger.debug('tenant.resolve.bypass', extra={'host': host, 'path': request.path})
            return None

        slug = parts[0].lower()
        tenant = Tenant.objects.filter(slug=slug, status='active', is_active=True).first()
        if not tenant:
            raise Http404('Tenant not found')

        request.tenant = tenant
        request.tenant_id = tenant.id

        tenant_user = None
        user = getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False):
            tenant_user = (
                TenantUser.objects.filter(
                    tenant=tenant, user=user, is_active=True
                ).first()
            )
        request.tenant_user = tenant_user
        logger.debug(
            'tenant.resolve',
            extra={'host': host, 'slug': slug, 'tenant': getattr(tenant, "id", None)},
        )
        set_current_tenant(tenant)
        return None


class TenantContextMiddleware(MiddlewareMixin):
    """Load tenant information from JWT claims or headers."""

    def __init__(self, get_response=None):
        """Initialize token backend."""
        super().__init__(get_response)
        self.token_backend = TokenBackend(
            algorithm=api_settings.ALGORITHM,
            signing_key=api_settings.SIGNING_KEY,
            verifying_key=api_settings.VERIFYING_KEY,
            audience=api_settings.AUDIENCE,
            issuer=api_settings.ISSUER,
            leeway=api_settings.LEEWAY,
        )

    def process_request(self, request):
        """Attach tenant to request and thread-local context."""
        # If a previous middleware (subdomain) already set tenant, respect it.
        if getattr(request, 'tenant', None):
            set_current_tenant(request.tenant)
            # tenant_user might already be present; ensure a default attribute exists
            if not hasattr(request, 'tenant_user'):
                request.tenant_user = None
            request.tenant_role = getattr(request.tenant_user, 'role', None)
            return

        request.tenant = None
        request.tenant_user = None
        request.tenant_role = None
        claims = self._decode_token(request)

        tenant = None
        user_id = None
        role = None

        if claims:
            tenant_id = claims.get('tenant_id')
            user_id = claims.get(api_settings.USER_ID_CLAIM)
            role = claims.get('role')
            request.tenant_role = role

            if tenant_id is not None:
                tenant = self._get_tenant_from_identifier(tenant_id)

        override_target = request.headers.get('X-Tenant-Override')
        if override_target:
            if self._can_override(user_id, override_target):
                tenant = self._get_tenant_from_identifier(override_target)
                logger.info(
                    'Tenant override applied',
                    extra={
                        'user_id': user_id,
                        'target_tenant': override_target,
                        'path': request.path,
                    },
                )
                log_audit(
                    'TENANT_OVERRIDE',
                    tenant=tenant,
                    actor=getattr(request, 'user', None),
                    metadata={'target': override_target, 'path': request.path},
                )
            else:
                return HttpResponseForbidden('Tenant override not permitted')

        if tenant:
            request.tenant = tenant
            # set_tenant(tenant)  # Removed - django_tenants not used
            set_current_tenant(tenant)
        else:
            pass

    def process_response(self, request, response):
        """Ensure tenant context is cleared after response."""
        clear_current_tenant()
        return response

    def _decode_token(self, request) -> Optional[dict]:
        """Decode Authorization bearer token if present."""
        header = request.headers.get('Authorization') or request.headers.get(
            'authorization'
        )
        if not header:
            return None

        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None

        if parts[1].startswith(ServiceToken.TOKEN_PREFIX):
            # Service tokens are handled by ServiceTokenAuthentication
            return None

        try:
            return self.token_backend.decode(parts[1], verify=True)
        except (InvalidToken, TokenBackendError) as exc:
            logger.warning('Invalid auth token for tenant context: %s', exc)
            return None

    def _get_tenant_from_identifier(self, value) -> Optional[Tenant]:
        """Lookup tenant by id or slug."""
        if value is None:
            return None

        qs = Tenant.objects.all()
        try:
            return qs.filter(pk=int(value)).first()
        except (TypeError, ValueError):
            return qs.filter(slug=str(value)).first()

    def _can_override(self, user_id, target) -> bool:
        """Check if the user can override tenant context."""
        if user_id is None or target is None:
            return False

        tenant = self._get_tenant_from_identifier(target)
        if tenant is None:
            return False

        return TenantUser.objects.filter(
            user_id=user_id,
            tenant=tenant,
            role=TenantUser.Role.OWNER_ADMIN,
            is_active=True,
        ).exists()
