"""Tests for WhatsApp channel mapping APIs."""

from rest_framework.test import APIClient, APITestCase

from tenancy.models import ServiceToken, Tenant
from channels.models import Contact, Conversation, WhatsAppChannel


class WhatsAppEndpointsTest(APITestCase):
    """Validate resolve and upsert flows."""

    def setUp(self):
        """Set up tenant, channel and tokens."""
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name='WA Tenant', slug='wa-tenant')
        self.channel = WhatsAppChannel.objects.create(
            tenant=self.tenant, phone_number_id='pn_1', display_number='+49123'
        )

        self.token_raw = ServiceToken.generate_token()
        self.token = ServiceToken.objects.create(name='bot', tenant=self.tenant)
        self.token.set_token(self.token_raw)
        self.token.save()

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_raw}')

    def test_resolve_maps_channel(self):
        """Resolve endpoint returns tenant mapping."""
        response = self.client.get(
            '/api/whatsapp/resolve/', {'phone_number_id': self.channel.phone_number_id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['tenant_id'], self.tenant.id)

    def test_contact_upsert_scoped(self):
        """Contacts are upserted within tenant."""
        payload = {'wa_id': 'wa-123', 'name': 'Alice', 'type': 'CUSTOMER'}
        response = self.client.post(
            '/api/whatsapp/contacts/upsert/', payload, format='json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()['contact']
        self.assertEqual(data['wa_id'], payload['wa_id'])
        self.assertEqual(data['tenant'], self.tenant.id)

        # Ensure unique per tenant
        self.assertEqual(
            Contact.objects.filter(tenant=self.tenant, wa_id=payload['wa_id']).count(),
            1,
        )

    def test_conversation_upsert_creates_and_updates_state(self):
        """Conversation upsert sets state and touch timestamp."""
        payload = {'wa_id': 'wa-321', 'state_json': {'step': 'start'}}
        response = self.client.post(
            '/api/whatsapp/conversations/upsert/', payload, format='json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()['conversation']
        self.assertEqual(data['contact']['wa_id'], payload['wa_id'])

        # Update with new state
        payload['state_json'] = {'step': 'next'}
        response = self.client.post(
            '/api/whatsapp/conversations/upsert/', payload, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Conversation.objects.filter(tenant=self.tenant).count(),
            1,
        )


class GlobalServiceTokenTests(APITestCase):
    """Service tokens without tenant can use phone_number_id to scope."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name='Second Tenant', slug='second-tenant')
        self.channel = WhatsAppChannel.objects.create(
            tenant=self.tenant, phone_number_id='pn_global', display_number='+49321'
        )
        self.raw_token = ServiceToken.generate_token()
        self.token = ServiceToken.objects.create(name='global', tenant=None)
        self.token.set_token(self.raw_token)
        self.token.save()

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.raw_token}')

    def test_global_token_resolves_tenant(self):
        """Global service token can resolve tenant via phone_number_id."""
        response = self.client.post(
            '/api/whatsapp/contacts/upsert/?phone_number_id=pn_global',
            {'wa_id': 'wa-global'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['contact']['tenant'], self.tenant.id)
