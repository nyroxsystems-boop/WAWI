"""Authentication tests for tenancy endpoints."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import path

from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient, APITestCase
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.authentication import CookieJWTAuthentication, ServiceTokenAuthentication
from tenancy.models import ServiceToken, Tenant, TenantUser
from tenancy.permissions import IsTenantMember, IsTenantOrServiceToken


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
    required_service_scope = 'bot.health.read'

    def get(self, request):
        """Return tenant context."""
        tenant = getattr(request, 'tenant', None)
        return Response({'tenant': tenant.id if tenant else None})


class CookieEchoView(APIView):
    """Unsafe echo used to assert CSRF enforcement for cookie JWTs."""

    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response({'ok': True})

    def post(self, request):
        return Response({'ok': True})


service_urlpatterns = [
    path('service-echo/', ServiceEchoView.as_view(), name='service-echo'),
    path('cookie-echo/', CookieEchoView.as_view(), name='cookie-echo'),
]
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
            name='bot', tenant=self.tenant, scopes=['bot.health.read']
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


@override_settings(ROOT_URLCONF=__name__)
class CookieJwtCsrfTests(APITestCase):
    """Cookie-carried JWTs require Django CSRF validation on unsafe methods."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='cookie-user', email='cookie@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(
            schema_name='cookie-tenant', name='Cookie Tenant', slug='cookie-tenant'
        )
        TenantUser.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantUser.Role.TENANT_ADMIN,
        )
        token = AccessToken.for_user(self.user)
        token['tenant_id'] = self.tenant.id
        token['role'] = TenantUser.Role.TENANT_ADMIN
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.cookies['access_token'] = str(token)

    def test_safe_cookie_request_is_allowed(self):
        response = self.client.get('/cookie-echo/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unsafe_cookie_request_without_csrf_is_rejected(self):
        response = self.client.post('/cookie-echo/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
