# Generated manually for service tokens
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('token_hash', models.CharField(db_index=True, max_length=128, unique=True)),
                ('scopes', models.JSONField(default=list, help_text='List of scopes for this token')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='service_tokens', to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Service Token',
                'verbose_name_plural': 'Service Tokens',
            },
        ),
    ]
