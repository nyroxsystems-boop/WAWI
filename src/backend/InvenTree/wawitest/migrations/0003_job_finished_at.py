from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wawitest', '0002_job_started_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='finished_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
