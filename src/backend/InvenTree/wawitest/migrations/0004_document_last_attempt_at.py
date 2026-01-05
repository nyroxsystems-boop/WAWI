from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wawitest', '0003_job_finished_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='last_attempt_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
