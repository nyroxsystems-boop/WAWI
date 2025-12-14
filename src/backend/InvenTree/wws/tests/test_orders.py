"""Tests for WWS orders and offers."""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from tenancy.models import Tenant, TenantUser
from wws.models import Offer, Order, Supplier, WwsConnection


class WwsOrderApiTests(APITestCase):
    """Ensure tenant scoped CRUD works."""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='wwsuser', email='wws@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Tenant A', slug='tenant-a')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )
        self.other_tenant = Tenant.objects.create(name='Tenant B', slug='tenant-b')
        TenantUser.objects.create(
            user=self.user, tenant=self.other_tenant, role='TENANT_ADMIN', is_active=True
        )

    def auth(self, tenant):
        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken.for_user(self.user)
        token['tenant_id'] = tenant.id
        token['role'] = 'TENANT_ADMIN'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')

    def test_order_crud_scoped(self):
        """Orders belong to tenant and cannot cross."""
        self.auth(self.tenant)
        create = self.client.post(
            '/api/orders/',
            {'external_ref': 'A1', 'status': 'new'},
            format='json',
        )
        self.assertEqual(create.status_code, 201)
        order_id = create.json()['id']

        list_resp = self.client.get('/api/orders/')
        self.assertEqual(len(list_resp.json()), 1)

        # Switch tenant and ensure no results
        self.auth(self.other_tenant)
        list_resp = self.client.get('/api/orders/')
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()), 0)

        # Detail forbidden for other tenant
        detail = self.client.get(f'/api/orders/{order_id}/')
        self.assertEqual(detail.status_code, 404)

    def test_offers_create_for_order(self):
        """Offers can be created for an order."""
        self.auth(self.tenant)
        supplier = Supplier.objects.create(tenant=self.tenant, name='Sup A')
        order = Order.objects.create(tenant=self.tenant, status='new')

        resp = self.client.post(
            f'/api/orders/{order.id}/offers/',
            {'supplier': supplier.id, 'price': '10.50', 'currency': 'EUR'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['orderId'], order.id)
        self.assertEqual(Offer.objects.filter(order=order).count(), 1)

    def test_connections_test_endpoint(self):
        """Test endpoint returns ok."""
        self.auth(self.tenant)
        conn = WwsConnection.objects.create(
            tenant=self.tenant, type=WwsConnection.ConnectionType.DEMO, base_url='http://demo'
        )
        resp = self.client.post(f'/api/wws-connections/{conn.id}/test/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')
