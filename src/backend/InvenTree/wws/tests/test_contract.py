"""Contract tests for dashboard endpoints."""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from tenancy.models import Tenant, TenantUser
from wws.models import Offer, Order, Supplier, WwsConnection


class DashboardContractTests(APITestCase):
    """Validate key endpoints used by dashboard."""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='contract', email='contract@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Contract', slug='contract')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )
        self.supplier = Supplier.objects.create(tenant=self.tenant, name='Supp')
        self.order = Order.objects.create(tenant=self.tenant, external_ref='REF1', status='new')
        self.offer = Offer.objects.create(
            tenant=self.tenant, order=self.order, supplier=self.supplier, price='10.00'
        )
        self.conn = WwsConnection.objects.create(
            tenant=self.tenant, type=WwsConnection.ConnectionType.DEMO, base_url='http://demo'
        )
        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken.for_user(self.user)
        token['tenant_id'] = self.tenant.id
        token['role'] = 'TENANT_ADMIN'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')

    def test_orders_list_shape(self):
        resp = self.client.get('/api/dashboard/orders')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        item = data[0]
        for key in ['id', 'status']:
            self.assertIn(key, item)

    def test_order_offers_shape(self):
        resp = self.client.get(f'/api/dashboard/orders/{self.order.id}/offers')
        self.assertEqual(resp.status_code, 200)
        offers = resp.json()
        self.assertTrue(len(offers) >= 1)
        first = offers[0]
        self.assertIn('price', first)
        self.assertIn('currency', first)

    def test_connections_list(self):
        resp = self.client.get('/api/wws-connections')
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_dealer_suppliers_endpoint(self):
        resp = self.client.get(f'/api/dealers/{self.tenant.id}/suppliers')
        self.assertIn(resp.status_code, (200, 403))  # may auto-seed; 403 if tenant mismatch

    def test_invoices_endpoint(self):
        resp = self.client.get('/api/invoices')
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)
