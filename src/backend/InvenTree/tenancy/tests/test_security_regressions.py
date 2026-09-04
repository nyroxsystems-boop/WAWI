"""Regression tests for critical tenant and token authorization boundaries."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.models import ServiceToken, Tenant, TenantUser
from users.models import ApiToken


User = get_user_model()


def owner_token(user, tenant):
    """Build a tenant-owner JWT for route tests."""
    token = AccessToken.for_user(user)
    token['tenant_id'] = tenant.id
    token['role'] = TenantUser.Role.OWNER_ADMIN
    return str(token)


class CriticalTenantAuthorizationTests(APITestCase):
    """Tenant owners must not gain platform or foreign-tenant authority."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(
            schema_name='security-a', name='Security A', slug='security-a'
        )
        cls.tenant_b = Tenant.objects.create(
            schema_name='security-b', name='Security B', slug='security-b'
        )
        cls.owner_a = User.objects.create_user(
            username='owner-a', email='owner-a@example.com', password='original-pass-1'
        )
        cls.victim = User.objects.create_user(
            username='victim-b', email='victim@example.com', password='victim-pass-1'
        )
        TenantUser.objects.create(
            tenant=cls.tenant_a,
            user=cls.owner_a,
            role=TenantUser.Role.OWNER_ADMIN,
            is_active=True,
        )
        TenantUser.objects.create(
            tenant=cls.tenant_b,
            user=cls.victim,
            role=TenantUser.Role.OWNER_ADMIN,
            is_active=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {owner_token(self.owner_a, self.tenant_a)}'
        )

    def test_owner_cannot_retrieve_foreign_tenant(self):
        response = self.client.get(
            reverse('tenant-detail', kwargs={'pk': self.tenant_b.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_cannot_add_user_to_foreign_tenant(self):
        response = self.client.post(
            reverse('tenant-create-user', kwargs={'pk': self.tenant_b.pk}),
            {
                'user_email': 'new-user@example.com',
                'password': 'A-long-new-password-123!',
                'role': TenantUser.Role.OWNER_ADMIN,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_existing_global_account_password_is_never_reset(self):
        response = self.client.post(
            reverse('tenant-create-user', kwargs={'pk': self.tenant_a.pk}),
            {
                'user_email': self.victim.email,
                'password': 'Attacker-selected-password-123!',
                'role': TenantUser.Role.OWNER_ADMIN,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.victim.refresh_from_db()
        self.assertTrue(self.victim.check_password('victim-pass-1'))
        self.assertFalse(
            TenantUser.objects.filter(
                tenant=self.tenant_a, user=self.victim
            ).exists()
        )

    def test_service_token_cannot_target_foreign_tenant(self):
        response = self.client.post(
            reverse('service-token-list'),
            {
                'name': 'foreign-pivot',
                'tenant_id': self.tenant_b.id,
                'scopes': ['billing.read'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ServiceToken.objects.filter(name='foreign-pivot').exists())

    def test_service_token_rejects_namespace_wildcard(self):
        response = self.client.post(
            reverse('service-token-list'),
            {'name': 'wild', 'scopes': ['bot:*']},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ApiTokenOwnershipTests(APITestCase):
    """The token-create serializer must bind ownership to request.user."""

    def test_posted_user_id_cannot_mint_token_for_another_user(self):
        attacker = User.objects.create_superuser(
            username='token-attacker',
            email='token-attacker@example.com',
            password='password-1',
        )
        victim = User.objects.create_superuser(
            username='token-victim',
            email='token-victim@example.com',
            password='password-2',
        )
        self.client.force_authenticate(user=attacker)

        response = self.client.post(
            reverse('api-token-list'),
            {'name': 'attempted-pivot', 'user': victim.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        token = ApiToken.objects.get(pk=response.data['id'])
        self.assertEqual(token.user_id, attacker.pk)
        self.assertNotEqual(token.user_id, victim.pk)
