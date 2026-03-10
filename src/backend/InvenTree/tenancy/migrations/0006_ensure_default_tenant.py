"""Ensure a default tenant and admin membership exist after migration.

After migrating from Render to Railway, the TenantUser records may not exist.
This migration creates:
1. A default 'demo' Tenant if none exist
2. A TenantUser membership for every superuser/staff member
"""

from django.db import migrations


def create_default_tenant_and_memberships(apps, schema_editor):
    """Create default tenant and link admin users."""
    Tenant = apps.get_model('tenancy', 'Tenant')
    TenantUser = apps.get_model('tenancy', 'TenantUser')
    User = apps.get_model('auth', 'User')

    # Ensure at least one tenant exists
    tenant = Tenant.objects.first()
    if not tenant:
        tenant = Tenant.objects.create(
            name='Demo',
            slug='demo',
            schema_name='demo',
            status='active',
            is_active=True,
            max_users=10,
            max_devices=20,
        )
        print(f'\n  [MIGRATION] Created default tenant: {tenant.name} (slug={tenant.slug})')

    # Ensure all superusers and staff have a membership
    admin_users = User.objects.filter(is_staff=True)
    for user in admin_users:
        membership, created = TenantUser.objects.get_or_create(
            user=user,
            tenant=tenant,
            defaults={
                'role': 'OWNER_ADMIN',
                'is_active': True,
            },
        )
        if created:
            print(f'  [MIGRATION] Created membership: {user.username} -> {tenant.name} (OWNER_ADMIN)')
        else:
            print(f'  [MIGRATION] Membership exists: {user.username} -> {tenant.name} ({membership.role})')


def reverse(apps, schema_editor):
    """No-op reverse — don't delete data."""
    pass


class Migration(migrations.Migration):
    """Data migration: ensure default tenant and admin memberships."""

    dependencies = [
        ('tenancy', '0005_tenant_schema_name'),
        ('auth', '__latest__'),
    ]

    operations = [
        migrations.RunPython(
            create_default_tenant_and_memberships,
            reverse,
        ),
    ]
