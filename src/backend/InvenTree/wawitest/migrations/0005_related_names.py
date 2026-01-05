from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wawitest', '0004_document_last_attempt_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='tenant',
            field=models.ForeignKey(on_delete=models.CASCADE, related_name='wawitest_documents', to='tenancy.tenant', db_index=True),
        ),
        migrations.AlterField(
            model_name='job',
            name='tenant',
            field=models.ForeignKey(on_delete=models.CASCADE, related_name='wawitest_jobs', to='tenancy.tenant', db_index=True),
        ),
    ]
