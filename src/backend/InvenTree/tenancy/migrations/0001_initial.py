# Generated manually for tenancy app
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Tenant',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('slug', models.SlugField(unique=True)),
                ('status', models.CharField(default='active', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Tenant',
                'verbose_name_plural': 'Tenants',
            },
        ),
        migrations.CreateModel(
            name='TenantUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('OWNER_ADMIN', 'OWNER_ADMIN'), ('TENANT_ADMIN', 'TENANT_ADMIN'), ('TENANT_USER', 'TENANT_USER')], max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='tenancy.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tenant_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Tenant User',
                'verbose_name_plural': 'Tenant Users',
                'unique_together': {('user', 'tenant')},
            },
        ),
    ]
