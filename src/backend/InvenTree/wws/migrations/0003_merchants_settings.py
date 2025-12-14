# Generated manually for merchant settings
from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wws', '0002_connection_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='MerchantSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('selected_shops', models.JSONField(blank=True, default=list)),
                ('margin_percent', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5)),
                ('price_profiles', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Merchant Settings',
                'verbose_name_plural': 'Merchant Settings',
                'unique_together': {('tenant',)},
            },
        ),
    ]
