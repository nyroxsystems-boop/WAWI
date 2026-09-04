"""Security regression tests for WWS role, secret, and SSRF boundaries."""

import base64
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.models import ServiceToken, Tenant, TenantUser
from wws.models import Product, WwsConnection
from wws.safe_http import UnsafeOutboundUrl, _resolve_public_address
from wws.serializers import WwsConnectionSerializer


User = get_user_model()


def jwt_for(user, tenant, role):
    token = AccessToken.for_user(user)
    token['tenant_id'] = tenant.id
    token['role'] = role
    return str(token)


class TenantRoleBoundaryTests(APITestCase):
    """Read-only members cannot mutate inventory or read financial data."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            schema_name='role-boundary', name='Role Boundary', slug='role-boundary'
        )
        self.user = User.objects.create_user(
            username='readonly-user', email='readonly@example.com', password='pass123'
        )
        TenantUser.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=TenantUser.Role.TENANT_USER,
            is_active=True,
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f'Bearer {jwt_for(self.user, self.tenant, TenantUser.Role.TENANT_USER)}'
            )
        )

    def test_readonly_member_cannot_create_product(self):
        response = self.client.post(
            '/api/products/',
            {'IPN': 'SEC-1', 'name': 'Blocked product'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_readonly_member_cannot_read_invoices(self):
        response = self.client.get('/api/billing/invoices/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ServiceScopeBoundaryTests(APITestCase):
    """A bot inventory token cannot pivot into billing."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            schema_name='scope-boundary', name='Scope Boundary', slug='scope-boundary'
        )
        raw = ServiceToken.generate_token()
        token = ServiceToken.objects.create(
            tenant=self.tenant,
            name='inventory-only',
            token_hash=ServiceToken.hash_token(raw),
            scopes=['bot.inventory.read'],
        )
        self.assertTrue(token.is_active)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {raw}')

    def test_inventory_scope_cannot_read_billing(self):
        response = self.client.get('/api/billing/invoices/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_inventory_scope_can_use_inventory_endpoint(self):
        response = self.client.get('/api/bot/inventory/by-oem/SEC-1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class WwsConnectionSecurityTests(APITestCase):
    """Connection secrets remain write-only and unsafe URLs are rejected."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            schema_name='connection-security',
            name='Connection Security',
            slug='connection-security',
        )

    def test_auth_config_is_not_serialized(self):
        connection = WwsConnection.objects.create(
            tenant=self.tenant,
            name='Secret connection',
            type=WwsConnection.ConnectionType.HTTP_API,
            base_url='https://supplier.example',
            auth_config_json={'token': 'do-not-return'},
        )
        data = WwsConnectionSerializer(connection).data
        self.assertNotIn('auth_config_json', data)
        self.assertNotIn('authConfig', data)
        self.assertNotIn('do-not-return', str(data))

    def test_private_ip_url_is_rejected(self):
        serializer = WwsConnectionSerializer(
            data={
                'name': 'Private target',
                'type': WwsConnection.ConnectionType.HTTP_API,
                'base_url': 'https://127.0.0.1',
                'config_json': {'inventory_path': '/inventory'},
            },
            context={'tenant': self.tenant},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('base_url', serializer.errors)

    @patch('wws.safe_http.socket.getaddrinfo')
    def test_dns_answer_containing_private_address_is_rejected(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, '', ('93.184.216.34', 443)),
            (2, 1, 6, '', ('127.0.0.1', 443)),
        ]
        with self.assertRaises(UnsafeOutboundUrl):
            _resolve_public_address('supplier.example', 443)


class ProtectedMediaBoundaryTests(APITestCase):
    """Media files are private and product images stay tenant-bound."""

    def setUp(self):
        self.temp_media = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.tenant = Tenant.objects.create(
            schema_name='media-owner', name='Media Owner', slug='media-owner'
        )
        self.other_tenant = Tenant.objects.create(
            schema_name='media-other', name='Media Other', slug='media-other'
        )
        self.user = User.objects.create_user(username='media-user', password='pass123')
        self.other_user = User.objects.create_user(username='media-other-user', password='pass123')
        TenantUser.objects.create(
            tenant=self.tenant, user=self.user,
            role=TenantUser.Role.TENANT_USER, is_active=True,
        )
        TenantUser.objects.create(
            tenant=self.other_tenant, user=self.other_user,
            role=TenantUser.Role.TENANT_USER, is_active=True,
        )
        self.product = Product.objects.create(
            tenant=self.tenant,
            IPN='MEDIA-1',
            name='Private product image',
            image=SimpleUploadedFile(
                'private.png',
                base64.b64decode(
                    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC'
                    'AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
                ),
            ),
        )
        self.url = f'/media/{self.product.image.name}'

    def test_media_is_not_public(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_other_tenant_cannot_read_product_image(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f'Bearer {jwt_for(self.other_user, self.other_tenant, TenantUser.Role.TENANT_USER)}'
            )
        )
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_tenant_can_read_product_image_without_public_caching(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f'Bearer {jwt_for(self.user, self.tenant, TenantUser.Role.TENANT_USER)}'
            )
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_executable_content_with_image_extension_is_rejected(self):
        executable = Product.objects.create(
            tenant=self.tenant,
            IPN='MEDIA-2',
            name='Not really an image',
            image=SimpleUploadedFile('disguised.png', b'MZnot-an-image'),
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f'Bearer {jwt_for(self.user, self.tenant, TenantUser.Role.TENANT_USER)}'
            )
        )
        self.assertEqual(
            self.client.get(f'/media/{executable.image.name}').status_code,
            status.HTTP_404_NOT_FOUND,
        )
