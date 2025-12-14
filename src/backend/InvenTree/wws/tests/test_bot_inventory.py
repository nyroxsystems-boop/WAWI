"""Tests for bot inventory endpoint."""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from tenancy.models import Tenant, TenantUser
from wws.models import WwsConnection


class BotInventoryTests(APITestCase):
    """Ensure endpoint is tenant-scoped and uses adapters."""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='botuser', email='bot@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Tenant Bot', slug='tenant-bot')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )

    def auth(self, tenant):
        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken.for_user(self.user)
        token['tenant_id'] = tenant.id
        token['role'] = 'TENANT_ADMIN'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')

    def test_demo_adapter_returns_offers(self):
        """Demo adapter should return mock offers."""
        self.auth(self.tenant)
        WwsConnection.objects.create(
            tenant=self.tenant,
            type=WwsConnection.ConnectionType.DEMO,
            base_url='http://demo',
            config_json={'supplier_name': 'Demo Supplier'},
        )

        resp = self.client.get('/api/bot/inventory/by-oem/12345')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['oem'], '12345')
        self.assertTrue(len(data['offers']) >= 1)
        self.assertEqual(data['offers'][0]['supplier_name'], 'Demo Supplier')

    def test_missing_tenant_forbidden(self):
        """Reject requests without tenant context."""
        resp = self.client.get('/api/bot/inventory/by-oem/abc')
        self.assertEqual(resp.status_code, 403)
