"""Billing tests for invoices."""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from tenancy.models import Tenant, TenantUser
from billing.models import Invoice, InvoiceSequence


class InvoiceApiTests(APITestCase):
    """Ensure invoices behave correctly."""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='bill', email='bill@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Bill Tenant', slug='bill-tenant')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )

    def auth(self, tenant):
        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken.for_user(self.user)
        token['tenant_id'] = tenant.id
        token['role'] = 'TENANT_ADMIN'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')

    def test_invoice_issue_sets_number(self):
        """Issue transition assigns number and totals."""
        self.auth(self.tenant)
        resp = self.client.post('/api/invoices/', {'status': 'DRAFT'}, format='json')
        self.assertEqual(resp.status_code, 201)
        invoice_id = resp.json()['id']

        issue = self.client.post(f'/api/invoices/{invoice_id}/issue/')
        self.assertEqual(issue.status_code, 200)
        data = issue.json()
        self.assertTrue(data['invoice_number'])
        self.assertEqual(data['status'], 'ISSUED')

    def test_numbering_isolated_per_tenant(self):
        """Sequences per tenant should increment separately."""
        self.auth(self.tenant)
        inv1 = Invoice.objects.create(tenant=self.tenant)
        inv1.issue()

        other_tenant = Tenant.objects.create(name='Other', slug='other')
        InvoiceSequence.objects.create(tenant=other_tenant, prefix='RE-')
        inv2 = Invoice.objects.create(tenant=other_tenant)
        inv2.issue()

        self.assertNotEqual(inv1.invoice_number, inv2.invoice_number)

    def test_cannot_cancel_paid(self):
        """Paid invoices cannot be canceled."""
        invoice = Invoice.objects.create(tenant=self.tenant, status=Invoice.Status.PAID)
        with self.assertRaises(ValueError):
            invoice.cancel()
