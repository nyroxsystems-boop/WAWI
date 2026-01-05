"""Seed WWS demo data."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from channels.models import WhatsAppChannel
from billing.models import InvoiceSequence
from tenancy.models import ServiceToken, Tenant, TenantUser
from wws.models import Offer, Order, Supplier, WwsConnection


class Command(BaseCommand):
    """Seed command to bootstrap demo tenant and data."""

    help = 'Create demo tenant, user, WhatsApp channel, supplier, connection, order, offers'

    def handle(self, *args, **options):
        User = get_user_model()
        owner, _ = User.objects.get_or_create(
            username='owner',
            defaults={'email': 'owner@example.com', 'is_staff': True, 'is_superuser': True},
        )
        if not owner.password:
            owner.set_password('owner')
            owner.save()

        tenant, _ = Tenant.objects.get_or_create(name='Demo Händler', slug='demo-haendler')
        TenantUser.objects.get_or_create(
            user=owner,
            tenant=tenant,
            role=TenantUser.Role.TENANT_ADMIN,
            defaults={'is_active': True},
        )

        WhatsAppChannel.objects.get_or_create(
            tenant=tenant,
            phone_number_id='demo',
            defaults={'display_number': '+49123456789', 'status': 'active'},
        )

        supplier, _ = Supplier.objects.get_or_create(
            tenant=tenant, name='Demo Supplier', defaults={'api_type': 'demo', 'rating': 5}
        )

        WwsConnection.objects.get_or_create(
            tenant=tenant,
            type=WwsConnection.ConnectionType.DEMO,
            base_url='http://demo.example.com',
            defaults={'config_json': {'supplier_name': supplier.name}},
        )

        InvoiceSequence.objects.get_or_create(tenant=tenant, defaults={'prefix': 'RE-'})

        order, _ = Order.objects.get_or_create(
            tenant=tenant,
            external_ref='DEMO-ORDER-2',
            defaults={'status': 'new', 'oem': '11428507683', 'currency': 'EUR'},
        )
        Offer.objects.get_or_create(
            tenant=tenant,
            order=order,
            supplier=supplier,
            defaults={
                'price': '129.90',
                'currency': 'EUR',
                'product_name': 'Demo Angebot',
                'availability': 'in_stock',
                'delivery_days': 2,
            },
        )

        token_value = ServiceToken.generate_token()
        svc, created = ServiceToken.objects.get_or_create(
            tenant=tenant,
            name='bot-service',
            defaults={'token_hash': ServiceToken.hash_token(token_value), 'scopes': ['bot:*']},
        )

        self.stdout.write(self.style.SUCCESS('Seed WWS demo data created'))
        self.stdout.write(f'Tenant ID: {tenant.id}')
        self.stdout.write(f'Owner username: {owner.username} / password: owner')
        if created:
            self.stdout.write(f'Service token: {token_value}')
        else:
            self.stdout.write('Service token already existed (not shown)')
