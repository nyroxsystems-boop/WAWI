# Generated manually for WWS app
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('channels', '0001_initial'),
        ('tenancy', '0002_servicetoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('rating', models.DecimalField(decimal_places=2, default=Decimal('0.0'), max_digits=3)),
                ('api_type', models.CharField(blank=True, default='', max_length=50)),
                ('meta_json', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Supplier',
                'verbose_name_plural': 'Suppliers',
                'unique_together': {('tenant', 'name')},
            },
        ),
        migrations.CreateModel(
            name='WwsConnection',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('http_api', 'http_api'), ('scraper', 'scraper'), ('demo_wws', 'demo_wws')], max_length=20)),
                ('base_url', models.URLField(blank=True)),
                ('auth_config_json', models.JSONField(blank=True, default=dict)),
                ('config_json', models.JSONField(blank=True, default=dict)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'WWS Connection',
                'verbose_name_plural': 'WWS Connections',
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_ref', models.CharField(blank=True, max_length=100)),
                ('status', models.CharField(default='new', max_length=64)),
                ('language', models.CharField(blank=True, default='', max_length=8)),
                ('order_data', models.JSONField(blank=True, default=dict)),
                ('vehicle_json', models.JSONField(blank=True, default=dict)),
                ('part_json', models.JSONField(blank=True, default=dict)),
                ('oem', models.CharField(blank=True, max_length=64)),
                ('notes', models.TextField(blank=True)),
                ('total_price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('currency', models.CharField(default='EUR', max_length=8)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='channels.contact')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Order',
                'verbose_name_plural': 'Orders',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Offer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('currency', models.CharField(default='EUR', max_length=8)),
                ('availability', models.CharField(blank=True, max_length=128)),
                ('delivery_days', models.IntegerField(blank=True, null=True)),
                ('sku', models.CharField(blank=True, max_length=100)),
                ('product_name', models.CharField(blank=True, max_length=255)),
                ('brand', models.CharField(blank=True, max_length=100)),
                ('product_url', models.URLField(blank=True)),
                ('status', models.CharField(choices=[('draft', 'draft'), ('published', 'published')], default='draft', max_length=20)),
                ('meta_json', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offers', to='wws.order')),
                ('supplier', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='offers', to='wws.supplier')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Offer',
                'verbose_name_plural': 'Offers',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DealerSupplierSetting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=True)),
                ('priority', models.IntegerField(default=10)),
                ('is_default', models.BooleanField(default=False)),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dealer_settings', to='wws.supplier')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Dealer Supplier Setting',
                'verbose_name_plural': 'Dealer Supplier Settings',
                'ordering': ['priority'],
                'unique_together': {('tenant', 'supplier')},
            },
        ),
    ]
