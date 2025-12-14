# Generated manually to add name field
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wws', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='wwsconnection',
            name='name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['tenant', 'created_at'], name='order_tenant_created'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['tenant', 'status'], name='order_tenant_status'),
        ),
    ]
