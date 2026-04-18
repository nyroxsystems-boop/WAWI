"""Re-enforce tenant NOT NULL on all wws models.

Migration 0005 made `tenant` nullable on six models, which breaks the
multi-tenancy invariant: a row with tenant=NULL is either invisible to
every tenant (when a tenant context is active and the queryset filter
`tenant=<id>` excludes it) or visible to every tenant (when no context
is active). Neither is acceptable for a SaaS with 100 dealers.

Strategy:
    1. Backfill: any NULL tenant_id row is moved to a sentinel "orphan"
       tenant with slug='__orphan__' (is_active=False). These rows become
       inaccessible through normal APIs but remain recoverable manually.
    2. Alter the FK back to NOT NULL.

The sentinel tenant is created idempotently so the migration is safe to
run multiple times.
"""

import django.db.models.deletion
from django.db import migrations, models


def backfill_orphans(apps, schema_editor):
    Tenant = apps.get_model('tenancy', 'Tenant')
    orphan, _ = Tenant.objects.get_or_create(
        slug='__orphan__',
        defaults={
            'schema_name': '__orphan__',
            'name': 'Orphan rows (data migration sentinel)',
            'status': 'inactive',
            'is_active': False,
        },
    )

    tables = [
        ('DealerSupplierSetting', 'wws'),
        ('MerchantSettings', 'wws'),
        ('Offer', 'wws'),
        ('Order', 'wws'),
        ('Supplier', 'wws'),
        ('WwsConnection', 'wws'),
    ]
    for model_name, app in tables:
        Model = apps.get_model(app, model_name)
        Model.objects.filter(tenant__isnull=True).update(tenant=orphan)


def reverse_noop(apps, schema_editor):
    # Intentionally no-op: reversing this migration would require restoring
    # the nullable FK, but the data is safe either way.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0004_tenant_max_devices_tenant_max_users_tenantdevice'),
        ('wws', '0005_alter_dealersuppliersetting_tenant_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_orphans, reverse_noop),
        migrations.AlterField(
            model_name='dealersuppliersetting',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wws_dealersuppliersetting_set', to='tenancy.tenant'),
        ),
        migrations.AlterField(
            model_name='merchantsettings',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wws_merchantsettings_set', to='tenancy.tenant'),
        ),
        migrations.AlterField(
            model_name='offer',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wws_offer_set', to='tenancy.tenant'),
        ),
        migrations.AlterField(
            model_name='order',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wws_order_set', to='tenancy.tenant'),
        ),
        migrations.AlterField(
            model_name='supplier',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wws_supplier_set', to='tenancy.tenant'),
        ),
        migrations.AlterField(
            model_name='wwsconnection',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wws_wwsconnection_set', to='tenancy.tenant'),
        ),
    ]
