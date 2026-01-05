"""Authentication tests for tenancy endpoints."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import path

from rest_framework.response import Response
from rest_framework.test import APIClient, APITestCase
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.authentication import ServiceTokenAuthentication
from tenancy.models import ServiceToken, Tenant, TenantUser
from tenancy.permissions import IsTenantOrServiceToken


class LoginAuthTests(APITestCase):
    """Ensure JWT login flow works."""

    def setUp(self):
        """Create user and tenant fixtures."""
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='dash', email='dash@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Tenant Login', slug='tenant-login')
        self.membership = TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role=TenantUser.Role.TENANT_ADMIN
        )

    def test_login_returns_tokens(self):
        """Login returns access/refresh and embeds tenant claims."""
        response = self.client.post(
            '/api/auth/login/',
            {'email': self.user.email, 'password': 'pass123'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        token = AccessToken(response.data['access'])
        self.assertEqual(token['tenant_id'], self.tenant.id)
        self.assertEqual(token['role'], self.membership.role)

    def test_refresh_preserves_claims(self):
        """Refresh should keep tenant claims."""
        login = self.client.post(
            '/api/auth/login/',
            {'email': self.user.email, 'password': 'pass123'},
            format='json',
        )
        refresh = login.data['refresh']

        refreshed = self.client.post(
            '/api/auth/refresh/', {'refresh': refresh}, format='json'
        )

        self.assertEqual(refreshed.status_code, 200)
        token = AccessToken(refreshed.data['access'])
        self.assertEqual(token['tenant_id'], self.tenant.id)
        self.assertEqual(token['role'], self.membership.role)

    def test_login_without_membership_rejected(self):
        """User without tenant membership cannot log in."""
        user = get_user_model().objects.create_user(
            username='nomember', email='nomember@example.com', password='pass123'
        )
        response = self.client.post(
            '/api/auth/login/',
            {'email': user.email, 'password': 'pass123'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)


class ServiceEchoView(APIView):
    """Simple view to confirm service token auth."""

    authentication_classes = [ServiceTokenAuthentication]
    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        """Return tenant context."""
        tenant = getattr(request, 'tenant', None)
        return Response({'tenant': tenant.id if tenant else None})


service_urlpatterns = [path('service-echo/', ServiceEchoView.as_view(), name='service-echo')]
urlpatterns = service_urlpatterns


@override_settings(ROOT_URLCONF=__name__)
class ServiceTokenTests(APITestCase):
    """Validate service token authentication."""

    def setUp(self):
        """Create tenant and service token."""
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name='Service Tenant', slug='service-tenant')
        self.raw_token = ServiceToken.generate_token()
        self.token = ServiceToken.objects.create(
            name='bot', tenant=self.tenant, scopes=['bot:*']
        )
        self.token.set_token(self.raw_token)
        self.token.save()

    def test_service_token_sets_tenant(self):
        """Service token should authenticate and set tenant context."""
        response = self.client.get(
            '/service-echo/', HTTP_AUTHORIZATION=f'Bearer {self.raw_token}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tenant'], self.tenant.id)

    def test_invalid_service_token_rejected(self):
        """Invalid tokens are rejected."""
        response = self.client.get(
            '/service-echo/', HTTP_AUTHORIZATION='Bearer svc_invalid'
        )
        self.assertEqual(response.status_code, 401)
