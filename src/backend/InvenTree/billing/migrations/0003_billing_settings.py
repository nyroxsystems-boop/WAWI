# Generated manually for billing settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0002_servicetoken'),
        ('billing', '0002_unique_invoice_number'),
    ]

    operations = [
        migrations.CreateModel(
            name='BillingSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_name', models.CharField(max_length=255)),
                ('address_line1', models.CharField(max_length=255)),
                ('address_line2', models.CharField(blank=True, default='', max_length=255)),
                ('city', models.CharField(max_length=128)),
                ('postal_code', models.CharField(max_length=32)),
                ('country', models.CharField(blank=True, default='', max_length=64)),
                ('tax_id', models.CharField(blank=True, default='', max_length=64)),
                ('iban', models.CharField(blank=True, default='', max_length=64)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('phone', models.CharField(blank=True, default='', max_length=64)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Billing Settings',
                'verbose_name_plural': 'Billing Settings',
            },
        ),
    ]
