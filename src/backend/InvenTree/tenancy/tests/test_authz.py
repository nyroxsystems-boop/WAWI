"""Tests for authz helpers."""

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import TestCase

from tenancy.authz import require_role, require_tenant
from tenancy.models import Tenant, TenantUser


def dummy_view(request):
    return HttpResponse('ok')


class AuthzTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug='t1', name='T1', status='active', is_active=True)
        User = get_user_model()
        self.user_staff = User.objects.create_user(username='staff', email='s@example.com', password='x')
        self.user_ro = User.objects.create_user(username='ro', email='r@example.com', password='x')
        TenantUser.objects.create(tenant=self.tenant, user=self.user_staff, role=TenantUser.Role.TENANT_ADMIN, is_active=True)
        TenantUser.objects.create(tenant=self.tenant, user=self.user_ro, role=TenantUser.Role.TENANT_USER, is_active=True)

    def _request_with_user(self, user):
        class R:
            pass
        req = R()
        req.user = user
        req.tenant = self.tenant
        req.tenant_user = TenantUser.objects.filter(tenant=self.tenant, user=user).first()
        return req

    def test_require_tenant_blocks_none(self):
        view = require_tenant(dummy_view)
        class R: pass
        req = R()
        req.tenant = None
        resp = view(req)
        self.assertEqual(resp.status_code, 403)

    def test_readonly_blocked_on_staff(self):
        view = require_role('staff')(dummy_view)
        req = self._request_with_user(self.user_ro)
        resp = view(req)
        self.assertEqual(resp.status_code, 403)

    def test_staff_allowed(self):
        view = require_role('staff')(dummy_view)
        req = self._request_with_user(self.user_staff)
        resp = view(req)
        self.assertEqual(resp.status_code, 200)
