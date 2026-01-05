"""Events/outbox app config."""

from django.apps import AppConfig


class OutboxConfig(AppConfig):
    """Config for outbox events."""

    name = 'outbox'
