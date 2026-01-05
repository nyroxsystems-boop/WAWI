# Generated manually for WAWI test harness
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenancy', '0002_servicetoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_id', models.CharField(db_index=True, max_length=100)),
                ('doc_type', models.CharField(max_length=50)),
                ('version', models.PositiveIntegerField(default=1)),
                ('status', models.CharField(choices=[('creating', 'creating'), ('ready', 'ready'), ('failed', 'failed')], default='creating', max_length=20)),
                ('dedupe_key', models.CharField(blank=True, db_index=True, max_length=128, null=True)),
                ('last_error', models.TextField(blank=True, default='')),
                ('created_by_user_id', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='WawiConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('base_url', models.CharField(blank=True, default='', max_length=255)),
                ('api_token', models.CharField(blank=True, default='', max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='wawi_config', to='tenancy.tenant')),
            ],
        ),
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('queued', 'queued'), ('running', 'running'), ('done', 'done'), ('failed', 'failed')], default='queued', max_length=20)),
                ('retry_count', models.PositiveIntegerField(default=0)),
                ('max_retries', models.PositiveIntegerField(default=3)),
                ('last_error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='jobs', to='wawitest.document')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenancy.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='document',
            constraint=models.UniqueConstraint(fields=('tenant', 'order_id', 'doc_type', 'version'), name='uniq_doc_order_type_version'),
        ),
        migrations.AddConstraint(
            model_name='document',
            constraint=models.UniqueConstraint(condition=models.Q(('dedupe_key__isnull', False)), fields=('tenant', 'dedupe_key'), name='uniq_doc_dedupe_per_tenant'),
        ),
    ]
