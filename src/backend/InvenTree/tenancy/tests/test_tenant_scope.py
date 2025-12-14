"""Tests for tenancy middleware and scoping."""

from django.contrib.auth import get_user_model
from django.db import connection, models
from django.test import TestCase, override_settings
from django.urls import path

from rest_framework.response import Response
from rest_framework.test import APIClient, APITestCase
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.context import clear_current_tenant, set_current_tenant
from tenancy.models import Tenant, TenantScopedModel, TenantUser
from tenancy.permissions import IsTenantMember


class TenantEchoView(APIView):
    """Simple view that echoes the tenant id."""

    permission_classes = [IsTenantMember]

    def get(self, request):
        """Return tenant info for testing."""
        return Response({'tenant': getattr(request, 'tenant', None).id})


test_urlpatterns = [path('tenant-echo/', TenantEchoView.as_view(), name='tenant-echo')]
urlpatterns = test_urlpatterns


class TenantScopedManagerTest(TestCase):
    """Ensure queryset scoping honours tenant context."""

    def setUp(self):
        """Create a temporary model table for testing."""
        class DummyModel(TenantScopedModel):
            name = models.CharField(max_length=32)

            class Meta:
                app_label = 'tenancy'

        self.Model = DummyModel
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(self.Model)

        self.tenant_a = Tenant.objects.create(name='Tenant A', slug='tenant-a')
        self.tenant_b = Tenant.objects.create(name='Tenant B', slug='tenant-b')

    def tearDown(self):
        """Drop the temporary model table and clear context."""
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(self.Model)
        clear_current_tenant()

    def test_queryset_respects_context(self):
        """Manager should scope queries when a tenant is set."""
        a_obj = self.Model.objects.create(tenant=self.tenant_a, name='a')
        self.Model.objects.create(tenant=self.tenant_b, name='b')

        set_current_tenant(self.tenant_a)
        self.assertEqual(self.Model.objects.count(), 1)
        self.assertEqual(self.Model.objects.first().id, a_obj.id)

        clear_current_tenant()
        self.assertEqual(self.Model.objects.count(), 2)
        self.assertEqual(self.Model.objects.for_tenant(self.tenant_a).count(), 1)


@override_settings(ROOT_URLCONF=__name__)
class TenantMiddlewareTest(APITestCase):
    """Validate tenant middleware populates request context."""

    def setUp(self):
        """Create user and tenant fixtures."""
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='member', email='member@example.com', password='pass'
        )
        self.tenant = Tenant.objects.create(name='Tenant One', slug='tenant-one')
        self.member = TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role=TenantUser.Role.TENANT_USER
        )

    def build_token(self, tenant, role):
        """Create a JWT with tenant and role claims."""
        token = AccessToken.for_user(self.user)
        token['tenant_id'] = tenant.id
        token['role'] = role
        return str(token)

    def test_missing_tenant_denied(self):
        """Request without tenant claim is forbidden."""
        response = self.client.get('/tenant-echo/')
        self.assertIn(response.status_code, (401, 403))

    def test_tenant_from_jwt(self):
        """Middleware should set tenant from JWT claim."""
        token = self.build_token(self.tenant, TenantUser.Role.TENANT_USER)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/tenant-echo/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tenant'], self.tenant.id)

    def test_owner_can_override_tenant(self):
        """Owner can target another tenant via override header."""
        other = Tenant.objects.create(name='Tenant Two', slug='tenant-two')
        TenantUser.objects.create(
            user=self.user, tenant=other, role=TenantUser.Role.OWNER_ADMIN
        )

        token = self.build_token(self.tenant, TenantUser.Role.OWNER_ADMIN)
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {token}', HTTP_X_TENANT_OVERRIDE=str(other.id)
        )
        response = self.client.get('/tenant-echo/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tenant'], other.id)

    def test_non_owner_cannot_override(self):
        """Override header should be rejected when role is insufficient."""
        other = Tenant.objects.create(name='Tenant Three', slug='tenant-three')
        token = self.build_token(self.tenant, TenantUser.Role.TENANT_USER)

        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {token}', HTTP_X_TENANT_OVERRIDE=str(other.id)
        )
        response = self.client.get('/tenant-echo/')

        self.assertEqual(response.status_code, 403)
