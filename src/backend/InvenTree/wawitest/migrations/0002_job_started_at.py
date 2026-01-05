from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wawitest', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
