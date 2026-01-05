# Generated manually for billing app
from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('wws', '0001_initial'),
        ('channels', '0001_initial'),
        ('tenancy', '0002_servicetoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='InvoiceSequence',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prefix', models.CharField(default='RE-', max_length=20)),
                ('next_number', models.IntegerField(default=1)),
                ('padding', models.IntegerField(default=6)),
                ('yearly_reset', models.BooleanField(default=True)),
                ('last_reset_year', models.IntegerField(blank=True, null=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Invoice Sequence',
                'verbose_name_plural': 'Invoice Sequences',
            },
        ),
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_number', models.CharField(blank=True, max_length=50, null=True)),
                ('status', models.CharField(choices=[('DRAFT', 'DRAFT'), ('ISSUED', 'ISSUED'), ('SENT', 'SENT'), ('PAID', 'PAID'), ('CANCELED', 'CANCELED')], db_index=True, default='DRAFT', max_length=20)),
                ('issue_date', models.DateField(blank=True, null=True)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('subtotal', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('tax_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('currency', models.CharField(default='EUR', max_length=8)),
                ('billing_address_json', models.JSONField(blank=True, default=dict)),
                ('shipping_address_json', models.JSONField(blank=True, default=dict)),
                ('pdf_file', models.FileField(blank=True, null=True, upload_to='invoices/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoices', to='channels.contact')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoices', to='wws.order')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Invoice',
                'verbose_name_plural': 'Invoices',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='InvoiceLine',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=255)),
                ('quantity', models.DecimalField(decimal_places=2, default=Decimal('1'), max_digits=10)),
                ('unit_price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('tax_rate', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5)),
                ('line_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='billing.invoice')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Invoice Line',
                'verbose_name_plural': 'Invoice Lines',
            },
        ),
    ]
