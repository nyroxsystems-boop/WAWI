# Generated manually for channels app
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenancy', '0002_servicetoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='Contact',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wa_id', models.CharField(max_length=64)),
                ('name', models.CharField(blank=True, max_length=200)),
                ('type', models.CharField(choices=[('CUSTOMER', 'CUSTOMER'), ('WORKSHOP', 'WORKSHOP'), ('DEALER', 'DEALER'), ('UNKNOWN', 'UNKNOWN')], default='UNKNOWN', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Contact',
                'verbose_name_plural': 'Contacts',
                'unique_together': {('tenant', 'wa_id')},
            },
        ),
        migrations.CreateModel(
            name='WhatsAppChannel',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number_id', models.CharField(max_length=64, unique=True)),
                ('display_number', models.CharField(blank=True, max_length=64)),
                ('provider', models.CharField(default='whatsapp', max_length=50)),
                ('webhook_secret', models.CharField(blank=True, max_length=128)),
                ('status', models.CharField(default='active', max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'WhatsApp Channel',
                'verbose_name_plural': 'WhatsApp Channels',
            },
        ),
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state_json', models.JSONField(blank=True, default=dict)),
                ('last_message_at', models.DateTimeField(blank=True, null=True)),
                ('contact', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conversations', to='channels.contact')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Conversation',
                'verbose_name_plural': 'Conversations',
                'unique_together': {('tenant', 'contact')},
            },
        ),
    ]
