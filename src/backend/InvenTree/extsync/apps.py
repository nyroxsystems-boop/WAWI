"""App config for extsync."""

from django.apps import AppConfig


class ExtsyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'extsync'
    verbose_name = 'External Sync'

