"""Create a tenant plus default groups and an owner admin user."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from tenancy.models import Tenant, TenantUser


class Command(BaseCommand):
    help = 'Create a tenant with default groups and an owner admin user'

    def add_arguments(self, parser):
        parser.add_argument('--slug', required=True, help='Tenant slug (subdomain)')
        parser.add_argument('--name', required=True, help='Tenant display name')
        parser.add_argument('--admin_email', required=True, help='Admin email/username')
        parser.add_argument('--admin_password', required=True, help='Admin password')

    def handle(self, *args, **options):
        slug = options['slug'].strip().lower()
        name = options['name'].strip()
        admin_email = options['admin_email'].strip()
        admin_password = options['admin_password']

        tenant, _created = Tenant.objects.get_or_create(
            slug=slug,
            defaults={'name': name, 'status': 'active', 'is_active': True},
        )

        # Ensure groups exist
        group_owner = self._ensure_group(slug, 'Owner')
        group_staff = self._ensure_group(slug, 'Staff')
        self._ensure_group(slug, 'ReadOnly')

        User = get_user_model()
        user_defaults = {User.EMAIL_FIELD if hasattr(User, 'EMAIL_FIELD') else 'email': admin_email}
        username_field = getattr(User, 'USERNAME_FIELD', 'username')
        user_defaults[username_field] = admin_email
        user, _ = User.objects.get_or_create(
            email=admin_email,
            defaults=user_defaults,
        )
        user.is_staff = True
        user.is_active = True
        if not admin_password:
            raise CommandError('admin_password cannot be empty')
        user.set_password(admin_password)
        user.save()

        tu, _ = TenantUser.objects.update_or_create(
            tenant=tenant,
            user=user,
            defaults={'role': TenantUser.Role.OWNER_ADMIN, 'is_active': True},
        )
        user.groups.add(group_owner)
        user.groups.add(group_staff)

        self.stdout.write(self.style.SUCCESS(f'Tenant {tenant.slug} ready; admin user {user} created.'))

    def _ensure_group(self, slug: str, label: str) -> Group:
        group, _ = Group.objects.get_or_create(name=f'{slug}:{label}')
        return group
