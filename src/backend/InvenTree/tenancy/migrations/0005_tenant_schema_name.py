# Generated manually to add missing schema_name field from TenantMixin

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0004_tenant_max_devices_tenant_max_users_tenantdevice'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='schema_name',
            field=models.CharField(db_index=True, max_length=63, unique=True, validators=[]),
        ),
    ]
