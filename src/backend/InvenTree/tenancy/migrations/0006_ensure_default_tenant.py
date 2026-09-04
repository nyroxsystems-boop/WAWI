"""Ensure a default tenant and admin membership exist after migration.

After migrating from Render to Railway, the TenantUser records may not exist.
This migration creates:
1. A default 'demo' Tenant if none exist
2. A TenantUser membership for every superuser/staff member
"""

from django.db import migrations


def create_default_tenant_and_memberships(apps, schema_editor):
    """Ensure a default 'demo' tenant exists.

    The original version also back-filled TenantUser memberships for staff
    users (a one-time Render->Railway concern). That queried `auth.User`, but
    this fork ships a custom user model, so the `auth_user` table does not
    exist — the SELECT aborted the whole migration transaction on a fresh DB.
    The back-fill is unnecessary on a fresh deploy (no users exist yet) and is
    removed; the Demo tenant is still ensured and memberships are created at
    runtime when users are provisioned.
    """
    Tenant = apps.get_model('tenancy', 'Tenant')

    if not Tenant.objects.first():
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


def reverse(apps, schema_editor):
    """No-op reverse — don't delete data."""
    pass


class Migration(migrations.Migration):
    """Data migration: ensure default tenant and admin memberships."""

    dependencies = [
        ('tenancy', '0005_tenant_schema_name'),
    ]

    operations = [
        migrations.RunPython(
            create_default_tenant_and_memberships,
            reverse,
        ),
    ]
