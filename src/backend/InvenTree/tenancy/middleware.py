"""Middleware to attach tenant context to each request."""

import logging
from typing import Optional

from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import InvalidToken, TokenBackendError
from rest_framework_simplejwt.settings import api_settings

from .context import clear_current_tenant, set_current_tenant
from .models import ServiceToken, Tenant, TenantUser
from audit.utils import log_audit

logger = logging.getLogger('inventree')


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
        request.tenant = None
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
            set_current_tenant(tenant)
        else:
            clear_current_tenant()

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
