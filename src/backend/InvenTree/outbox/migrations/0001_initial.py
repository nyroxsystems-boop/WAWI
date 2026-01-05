# Generated manually for outbox events
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenancy', '0002_servicetoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='OutboxEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(max_length=64)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('PENDING', 'PENDING'), ('SENT', 'SENT'), ('FAILED', 'FAILED')], default='PENDING', max_length=16)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='outbox_events', to='tenancy.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Outbox Event',
                'verbose_name_plural': 'Outbox Events',
            },
        ),
    ]
