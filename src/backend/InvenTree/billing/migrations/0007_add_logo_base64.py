# Generated manually for billing logo_base64 field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_billingsettings_accent_color_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='billingsettings',
            name='logo_base64',
            field=models.TextField(blank=True, default=''),
        ),
    ]
