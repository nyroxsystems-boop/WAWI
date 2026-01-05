"""Create a user bound to a tenant with a specific role."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from tenancy.models import Tenant, TenantUser

ROLE_MAP = {
    'owner': TenantUser.Role.OWNER_ADMIN,
    'staff': TenantUser.Role.TENANT_ADMIN,
    'readonly': TenantUser.Role.TENANT_USER,
}

GROUP_LABEL = {
    'owner': 'Owner',
    'staff': 'Staff',
    'readonly': 'ReadOnly',
}


class Command(BaseCommand):
    help = 'Create a user for a tenant with a role'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', required=True, help='Tenant slug')
        parser.add_argument('--email', required=True, help='User email/username')
        parser.add_argument('--password', required=True, help='User password')
        parser.add_argument('--role', required=True, choices=['owner', 'staff', 'readonly'])

    def handle(self, *args, **options):
        slug = options['tenant'].strip().lower()
        email = options['email'].strip()
        password = options['password']
        role_input = options['role']

        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            raise CommandError(f'Tenant {slug} not found')

        tenant_role = ROLE_MAP.get(role_input)
        if tenant_role is None:
            raise CommandError('Invalid role')

        User = get_user_model()
        user_defaults = {User.EMAIL_FIELD if hasattr(User, 'EMAIL_FIELD') else 'email': email}
        username_field = getattr(User, 'USERNAME_FIELD', 'username')
        user_defaults[username_field] = email
        user, _ = User.objects.get_or_create(
            email=email,
            defaults=user_defaults,
        )
        user.is_staff = False
        user.is_active = True
        if not password:
            raise CommandError('password cannot be empty')
        user.set_password(password)
        user.save()

        TenantUser.objects.update_or_create(
            tenant=tenant,
            user=user,
            defaults={'role': tenant_role, 'is_active': True},
        )

        group_label = GROUP_LABEL[role_input]
        group, _ = Group.objects.get_or_create(name=f'{slug}:{group_label}')
        user.groups.add(group)

        self.stdout.write(self.style.SUCCESS(f'User {user} added to tenant {tenant.slug} as {role_input}'))
