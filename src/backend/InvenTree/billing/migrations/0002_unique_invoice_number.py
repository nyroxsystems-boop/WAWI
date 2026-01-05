# Generated manually to add constraints and indexes
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='invoice_number',
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True),
        ),
        migrations.AlterUniqueTogether(
            name='invoice',
            unique_together={('tenant', 'invoice_number')},
        ),
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['tenant', 'status'], name='invoice_tenant_status'),
        ),
    ]
