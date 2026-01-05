"""Validate outbox events are created for key flows."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from outbox.models import OutboxEvent
from tenancy.models import Tenant, TenantUser


class OutboxEventTests(APITestCase):
    """Ensure ORDER_CREATED and INVOICE_ISSUED events are enqueued."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='outbox', email='outbox@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Outbox', slug='outbox')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )
        token = AccessToken.for_user(self.user)
        token['tenant_id'] = self.tenant.id
        token['role'] = 'TENANT_ADMIN'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')

    def test_order_creation_enqueues_event(self):
        resp = self.client.post('/api/orders/', {'status': 'new'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            OutboxEvent.objects.filter(
                tenant=self.tenant, event_type='ORDER_CREATED'
            ).exists()
        )

    def test_invoice_issue_enqueues_event(self):
        inv_resp = self.client.post('/api/invoices/', {'status': 'DRAFT'}, format='json')
        self.assertEqual(inv_resp.status_code, 201)
        inv_id = inv_resp.json()['id']

        issue_resp = self.client.post(f'/api/invoices/{inv_id}/issue/')
        self.assertEqual(issue_resp.status_code, 200)

        self.assertTrue(
            OutboxEvent.objects.filter(
                tenant=self.tenant,
                event_type='INVOICE_ISSUED',
                payload__invoice_id=inv_id,
            ).exists()
        )
