from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wawitest', '0005_related_names'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='tenant',
            field=models.ForeignKey(db_index=True, on_delete=models.CASCADE, related_name='wawitest_documents', related_query_name='wawitest_document', to='tenancy.tenant'),
        ),
        migrations.AlterField(
            model_name='job',
            name='tenant',
            field=models.ForeignKey(db_index=True, on_delete=models.CASCADE, related_name='wawitest_jobs', related_query_name='wawitest_job', to='tenancy.tenant'),
        ),
    ]
