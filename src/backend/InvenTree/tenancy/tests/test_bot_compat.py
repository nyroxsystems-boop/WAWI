"""Bot compatibility flow tests."""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from channels.models import WhatsAppChannel
from tenancy.models import ServiceToken, Tenant, TenantUser
from wws.models import WwsConnection


class BotCompatTests(APITestCase):
    """Simulate bot flows without bot changes."""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='botcompat', email='botcompat@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='Bot Compat', slug='bot-compat')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )
        self.channel = WhatsAppChannel.objects.create(
            tenant=self.tenant, phone_number_id='demo-bot', display_number='+49123'
        )
        WwsConnection.objects.create(
            tenant=self.tenant, type=WwsConnection.ConnectionType.DEMO, base_url='http://demo'
        )
        self.raw_token = ServiceToken.generate_token()
        self.token = ServiceToken.objects.create(
            tenant=self.tenant,
            name='bot',
            token_hash=ServiceToken.hash_token(self.raw_token),
            scopes=['bot:*'],
        )

    def auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.raw_token}')

    def test_bot_flow(self):
        self.auth()
        # resolve channel
        r = self.client.get('/api/whatsapp/resolve', {'phone_number_id': self.channel.phone_number_id})
        self.assertEqual(r.status_code, 200)
        # upsert contact
        c = self.client.post('/api/contacts/upsert', {'wa_id': 'wa123', 'name': 'Bot User'}, format='json')
        self.assertEqual(c.status_code, 200)
        # upsert conversation
        conv = self.client.post('/api/conversations/upsert', {'wa_id': 'wa123', 'state_json': {'step': 'start'}}, format='json')
        self.assertEqual(conv.status_code, 200)
        # inventory by oem
        inv = self.client.get('/api/bot/inventory/by-oem/11428507683')
        self.assertEqual(inv.status_code, 200)
        self.assertIn('offers', inv.json())
