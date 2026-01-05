"""Tests for subdomain tenant middleware."""

from django.http import HttpRequest
from django.test import TestCase

from tenancy.middleware import SubdomainTenantMiddleware
from tenancy.models import Tenant


class TenantMiddlewareTests(TestCase):
    def setUp(self):
        self.middleware = SubdomainTenantMiddleware(lambda r: r)
        self.tenant = Tenant.objects.create(slug='autohaus', name='Autohaus', status='active', is_active=True)

    def test_resolve_tenant(self):
        req = HttpRequest()
        req.META['HTTP_HOST'] = 'autohaus.euredomain.de'
        self.middleware.process_request(req)
        self.assertEqual(req.tenant, self.tenant)
        self.assertEqual(req.tenant_id, self.tenant.id)

    def test_unknown_tenant_404(self):
        req = HttpRequest()
        req.META['HTTP_HOST'] = 'unknown.euredomain.de'
        with self.assertRaises(Exception):
            self.middleware.process_request(req)

    def test_no_subdomain_sets_none(self):
        req = HttpRequest()
        req.META['HTTP_HOST'] = 'euredomain.de'
        self.middleware.process_request(req)
        self.assertIsNone(getattr(req, 'tenant', None))
        self.assertIsNone(getattr(req, 'tenant_user', None))
