"""Seed demo data for local development."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string

from channels.models import WhatsAppChannel
from billing.models import InvoiceSequence
from tenancy.models import ServiceToken, Tenant, TenantUser
from wws.models import Offer, Order, Supplier, WwsConnection


class Command(BaseCommand):
    """Create demo tenant, user, channel, supplier, and service token."""

    help = 'Seed demo data: owner user, tenant, tenant user, WhatsApp channel, supplier'

    def handle(self, *args, **options):
        """Execute seed routine."""
        User = get_user_model()

        owner, _ = User.objects.get_or_create(
            username='owner',
            defaults={
                'email': 'owner@example.com',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if not owner.password:
            owner.set_password('owner')
            owner.save()

        tenant, _ = Tenant.objects.get_or_create(name='Demo Tenant', slug='demo-tenant')
        TenantUser.objects.get_or_create(
            user=owner,
            tenant=tenant,
            role=TenantUser.Role.OWNER_ADMIN,
            defaults={'is_active': True},
        )

        channel, _ = WhatsAppChannel.objects.get_or_create(
            tenant=tenant,
            phone_number_id='demo-phone-number',
            defaults={'display_number': '+49123456789', 'status': 'active'},
        )

        supplier, _ = Supplier.objects.get_or_create(
            tenant=tenant,
            name='Demo Supplier',
            defaults={'api_type': 'demo', 'rating': 5},
        )

        WwsConnection.objects.get_or_create(
            tenant=tenant,
            type=WwsConnection.ConnectionType.DEMO,
            base_url='http://demo.example.com',
            defaults={'config_json': {'supplier_name': supplier.name}},
        )

        InvoiceSequence.objects.get_or_create(tenant=tenant, defaults={'prefix': 'RE-'})

        # Example order and offers
        order, _ = Order.objects.get_or_create(
            tenant=tenant,
            external_ref='DEMO-ORDER-1',
            defaults={'status': 'new', 'oem': '11428507683', 'currency': 'EUR'},
        )
        Offer.objects.get_or_create(
            tenant=tenant,
            order=order,
            supplier=supplier,
            defaults={
                'price': '99.90',
                'currency': 'EUR',
                'product_name': 'Demo Ersatzteil',
                'availability': 'in_stock',
            },
        )

        # Create or fetch a service token for bot usage
        token_value = ServiceToken.generate_token()
        svc, created = ServiceToken.objects.get_or_create(
            tenant=tenant,
            name='bot-service',
            defaults={'token_hash': ServiceToken.hash_token(token_value), 'scopes': ['bot:*']},
        )
        if not created:
            token_value = None  # don't print secrets if existing

        self.stdout.write(self.style.SUCCESS('Seed data created'))
        self.stdout.write(f'Tenant ID: {tenant.id}')
        self.stdout.write(f'Owner username: {owner.username} / password: owner')
        self.stdout.write(f'WhatsApp channel phone_number_id: {channel.phone_number_id}')
        self.stdout.write(f'Supplier: {supplier.name}')
        if token_value:
            self.stdout.write(f'Service token (save this): {token_value}')
        else:
            self.stdout.write('Service token already existed; not printing token value.')
