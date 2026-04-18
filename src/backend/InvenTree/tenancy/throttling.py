"""Custom DRF throttles that key per-tenant, not globally.

Rationale:
    Default DRF UserRateThrottle uses user.pk as the cache bucket, which is
    fine for a single-tenant app. For a multi-tenant SaaS with 100 dealers we
    must also bound bursts per *tenant* — otherwise a single dealer's bot can
    saturate the shared rate budget and starve everyone else.

Three scopes exposed:
    tenant_burst  — short burst window (per-tenant)
    tenant_sustained — sustained rate (per-tenant)
    oem_lookup    — hot OEM search endpoint, strict per-tenant budget
"""

from rest_framework.throttling import SimpleRateThrottle


class _TenantScopedThrottleBase(SimpleRateThrottle):
    """Base class that keys on tenant id + scope."""

    scope = ''

    def get_cache_key(self, request, view):
        tenant = getattr(request, 'tenant', None)
        tenant_id = getattr(tenant, 'id', None) if tenant else None

        # Service-token calls are keyed by (tenant, token_id) so a single
        # bot key cannot drain the whole tenant budget.
        svc = getattr(request, 'service_token', None)
        svc_id = getattr(svc, 'id', None) if svc else None

        if tenant_id is None:
            # No tenant context — fall back to IP so we don't accidentally
            # share the bucket with *every* anonymous caller.
            ident = self.get_ident(request)
            return f'throttle_{self.scope}_anon_{ident}'

        if svc_id is not None:
            return f'throttle_{self.scope}_t{tenant_id}_svc{svc_id}'

        user = getattr(request, 'user', None)
        user_id = getattr(user, 'pk', None) if user and user.is_authenticated else None
        if user_id is not None:
            return f'throttle_{self.scope}_t{tenant_id}_u{user_id}'

        ident = self.get_ident(request)
        return f'throttle_{self.scope}_t{tenant_id}_{ident}'


class TenantBurstThrottle(_TenantScopedThrottleBase):
    """Short-window burst throttle, per tenant."""

    scope = 'tenant_burst'


class TenantSustainedThrottle(_TenantScopedThrottleBase):
    """Long-window sustained throttle, per tenant."""

    scope = 'tenant_sustained'


class OemLookupThrottle(_TenantScopedThrottleBase):
    """Strict throttle for the bot OEM lookup endpoint."""

    scope = 'oem_lookup'
