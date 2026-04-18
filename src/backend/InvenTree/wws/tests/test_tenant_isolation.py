"""Cross-tenant isolation tests for wws endpoints.

These tests exist to catch the single most dangerous class of bug in a
multi-tenant SaaS: a view that forgets to scope its queryset to
request.tenant, causing data from tenant A to be served to tenant B.

Every wws ViewSet should have at least one "hostile read" test here that
logs in as tenant B and confirms tenant A's rows are invisible.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse, NoReverseMatch
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.models import Tenant, TenantUser, ServiceToken
from wws.models import (
    Offer, Order, Product, StockLocation, Supplier, WwsConnection,
)


User = get_user_model()


def _jwt_for(user, tenant, role=TenantUser.Role.TENANT_USER, can_override=False):
    token = AccessToken.for_user(user)
    token['tenant_id'] = tenant.id
    token['role'] = role
    if can_override:
        token['can_override'] = True
    return str(token)


class WwsCrossTenantIsolationTest(APITestCase):
    """Verify tenant A's data never leaks to tenant B through wws APIs."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(
            schema_name='ta', name='Tenant A', slug='tenant-a'
        )
        cls.tenant_b = Tenant.objects.create(
            schema_name='tb', name='Tenant B', slug='tenant-b'
        )

        cls.user_a = User.objects.create_user(
            username='alice', email='alice@a.com', password='pw'
        )
        cls.user_b = User.objects.create_user(
            username='bob', email='bob@b.com', password='pw'
        )
        TenantUser.objects.create(
            user=cls.user_a, tenant=cls.tenant_a,
            role=TenantUser.Role.TENANT_ADMIN,
        )
        TenantUser.objects.create(
            user=cls.user_b, tenant=cls.tenant_b,
            role=TenantUser.Role.TENANT_ADMIN,
        )

        # Seed rows under each tenant.
        cls.supplier_a = Supplier.objects.create(
            tenant=cls.tenant_a, name='Supplier A',
        )
        cls.supplier_b = Supplier.objects.create(
            tenant=cls.tenant_b, name='Supplier B',
        )
        cls.order_a = Order.objects.create(
            tenant=cls.tenant_a, external_ref='A-0001', oem='OEM-A',
        )
        cls.order_b = Order.objects.create(
            tenant=cls.tenant_b, external_ref='B-0001', oem='OEM-B',
        )
        cls.product_a = Product.objects.create(
            tenant=cls.tenant_a, IPN='IPN-A', name='Part A',
        )
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, IPN='IPN-B', name='Part B',
        )
        cls.connection_a = WwsConnection.objects.create(
            tenant=cls.tenant_a, type=WwsConnection.ConnectionType.DEMO,
            base_url='https://demo-a.example',
        )
        cls.connection_b = WwsConnection.objects.create(
            tenant=cls.tenant_b, type=WwsConnection.ConnectionType.DEMO,
            base_url='https://demo-b.example',
        )
        cls.offer_a = Offer.objects.create(
            tenant=cls.tenant_a, order=cls.order_a, supplier=cls.supplier_a,
            product_name='Offer A', price=10,
        )
        cls.offer_b = Offer.objects.create(
            tenant=cls.tenant_b, order=cls.order_b, supplier=cls.supplier_b,
            product_name='Offer B', price=20,
        )

    def setUp(self):
        self.client = APIClient()

    def _as(self, user, tenant):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {_jwt_for(user, tenant)}'
        )

    # ------------------------------------------------------------------
    # Generic "list a collection as tenant B, expect no tenant-A rows"
    # ------------------------------------------------------------------

    def _assert_only_b(self, url, field='id', expected_b_ids=None):
        """Fetch url as tenant B and assert only B rows are returned."""
        self._as(self.user_b, self.tenant_b)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        body = response.json()
        items = body if isinstance(body, list) else body.get('results', [])
        ids = {row.get(field) for row in items}
        if expected_b_ids is not None:
            self.assertTrue(ids.issubset(set(expected_b_ids)),
                            f'Tenant B saw foreign ids via {url}: {ids - set(expected_b_ids)}')

    def test_suppliers_are_tenant_scoped(self):
        try:
            url = reverse('supplier-list')
        except NoReverseMatch:
            self.skipTest('supplier-list route not registered')
        self._assert_only_b(url, expected_b_ids=[self.supplier_b.id])

    def test_orders_are_tenant_scoped(self):
        try:
            url = reverse('order-list')
        except NoReverseMatch:
            self.skipTest('order-list route not registered')
        self._assert_only_b(url, expected_b_ids=[self.order_b.id])

    def test_offers_are_tenant_scoped(self):
        try:
            url = reverse('offer-list')
        except NoReverseMatch:
            self.skipTest('offer-list route not registered')
        self._assert_only_b(url, expected_b_ids=[self.offer_b.id])

    def test_connections_are_tenant_scoped(self):
        try:
            url = reverse('wwsconnection-list')
        except NoReverseMatch:
            self.skipTest('wwsconnection-list route not registered')
        self._assert_only_b(url, expected_b_ids=[self.connection_b.id])

    # ------------------------------------------------------------------
    # Direct fetch of a foreign row must 404
    # ------------------------------------------------------------------

    def test_cannot_fetch_foreign_order_detail(self):
        try:
            url = reverse('order-detail', args=[self.order_a.id])
        except NoReverseMatch:
            self.skipTest('order-detail route not registered')
        self._as(self.user_b, self.tenant_b)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_fetch_foreign_supplier_detail(self):
        try:
            url = reverse('supplier-detail', args=[self.supplier_a.id])
        except NoReverseMatch:
            self.skipTest('supplier-detail route not registered')
        self._as(self.user_b, self.tenant_b)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # Tenant override: ordinary users can't pivot
    # ------------------------------------------------------------------

    def test_tenant_override_rejected_without_owner_role(self):
        token = _jwt_for(self.user_b, self.tenant_b)
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {token}',
            HTTP_X_TENANT_OVERRIDE=str(self.tenant_a.id),
        )
        try:
            url = reverse('order-list')
        except NoReverseMatch:
            self.skipTest('order-list route not registered')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_override_rejected_without_can_override_claim(self):
        # OWNER role alone is not enough — JWT must carry can_override=True.
        TenantUser.objects.create(
            user=self.user_b, tenant=self.tenant_a,
            role=TenantUser.Role.OWNER_ADMIN,
        )
        token = _jwt_for(
            self.user_b, self.tenant_b,
            role=TenantUser.Role.OWNER_ADMIN,
            can_override=False,
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {token}',
            HTTP_X_TENANT_OVERRIDE=str(self.tenant_a.id),
        )
        try:
            url = reverse('order-list')
        except NoReverseMatch:
            self.skipTest('order-list route not registered')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ServiceTokenHardeningTest(APITestCase):
    """Verify service tokens without tenant or with wildcard scopes are rejected."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            schema_name='svc', name='SVC Tenant', slug='svc-tenant',
        )

    def test_service_token_without_tenant_is_rejected(self):
        raw = ServiceToken.generate_token()
        token = ServiceToken(name='global-bot', tenant=None, scopes=['read'])
        token.set_token(raw)
        token.save()

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {raw}')
        response = client.get('/api/wws/connections/')
        self.assertIn(response.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_service_token_with_wildcard_scope_is_rejected(self):
        raw = ServiceToken.generate_token()
        token = ServiceToken(name='wildcard-bot', tenant=self.tenant, scopes=['*'])
        token.set_token(raw)
        token.save()

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {raw}')
        response = client.get('/api/wws/connections/')
        self.assertIn(response.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_has_scope_rejects_wildcard(self):
        token = ServiceToken(name='wild', tenant=self.tenant, scopes=['*'])
        self.assertFalse(token.has_scope('read'))
        self.assertFalse(token.has_scope('anything'))
