"""Validate key endpoints against expected shapes."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.models import Tenant, TenantUser
from wws.models import Offer, Order, Supplier, WwsConnection, MerchantSettings


class ContractSchemaTests(APITestCase):
    """Lightweight schema checks mirroring docs/dashboard-api-contract.md."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='schema', email='schema@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Schema', slug='schema')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )
        token = AccessToken.for_user(self.user)
        token['tenant_id'] = self.tenant.id
        token['role'] = 'TENANT_ADMIN'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')

        self.supplier = Supplier.objects.create(tenant=self.tenant, name='Supp')
        self.order = Order.objects.create(
            tenant=self.tenant,
            external_ref='R1',
            status='new',
            oem='OEM-1',
        )
        self.offer = Offer.objects.create(
            tenant=self.tenant,
            order=self.order,
            supplier=self.supplier,
            price='10.00',
            currency='EUR',
            product_name='Demo',
        )
        self.conn = WwsConnection.objects.create(
            tenant=self.tenant,
            type=WwsConnection.ConnectionType.DEMO,
            base_url='http://demo',
            config_json={'supplier_name': 'Demo WWS'},
        )
        MerchantSettings.objects.create(tenant=self.tenant, margin_percent=0.2)

    def test_orders_list_keys(self):
        resp = self.client.get('/api/orders')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        item = data[0]
        for key in ['id', 'status', 'created_at']:
            self.assertIn(key, item)

    def test_order_offers_keys(self):
        resp = self.client.get(f'/api/orders/{self.order.id}/offers')
        self.assertEqual(resp.status_code, 200)
        offers = resp.json()
        self.assertTrue(len(offers) >= 1)
        first = offers[0]
        for key in ['id', 'price', 'currency', 'supplierName', 'shopName', 'orderId']:
            self.assertIn(key, first)

    def test_wws_connections(self):
        resp = self.client.get('/api/wws-connections')
        self.assertEqual(resp.status_code, 200)
        item = resp.json()[0]
        for key in ['id', 'type', 'baseUrl', 'isActive']:
            self.assertIn(key, item)

    def test_bot_inventory_shape(self):
        resp = self.client.get('/api/bot/inventory/by-oem/OEM-1')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn('offers', body)
        self.assertIn('oemNumber', body)

    def test_merchant_settings(self):
        resp = self.client.get(f'/api/dashboard/merchant/settings/{self.tenant.id}')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in ['merchantId', 'selectedShops', 'marginPercent']:
            self.assertIn(key, body)

    def test_invoices_endpoint(self):
        # create draft
        inv_resp = self.client.post('/api/invoices', {'currency': 'EUR'}, format='json')
        self.assertIn(inv_resp.status_code, (200, 201))
        list_resp = self.client.get('/api/invoices')
        self.assertEqual(list_resp.status_code, 200)
        self.assertIsInstance(list_resp.json(), list)
