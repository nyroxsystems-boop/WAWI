"""Validate billing settings and invoice constraints."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from tenancy.models import Tenant, TenantUser
from billing.models import Invoice, InvoiceSequence
from billing.models_settings import BillingSettings


class InvoiceValidationTests(APITestCase):
    """Test invoice numbering and immutability."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='billtest', email='billtest@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Val', slug='val')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )

    def test_unique_number_per_tenant(self):
        InvoiceSequence.objects.create(tenant=self.tenant)
        inv1 = Invoice.objects.create(tenant=self.tenant)
        inv1.issue()
        inv2 = Invoice.objects.create(tenant=self.tenant)
        inv2.issue()
        self.assertNotEqual(inv1.invoice_number, inv2.invoice_number)

    def test_number_not_changeable(self):
        InvoiceSequence.objects.create(tenant=self.tenant)
        inv = Invoice.objects.create(tenant=self.tenant)
        inv.issue()
        inv.invoice_number = 'HACK'
        with self.assertRaises(ValidationError):
            inv.save()

    def test_settings_endpoint(self):
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken.for_user(self.user)
        token['tenant_id'] = self.tenant.id
        token['role'] = 'TENANT_ADMIN'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')

        resp = self.client.get('/api/settings/billing/1/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('company_name', resp.json())
