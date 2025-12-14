"""Outbox event model."""

from django.db import models
from django.utils import timezone

from tenancy.models import Tenant


class OutboxEvent(models.Model):
    """Store outbound events for webhooks/integrations."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'PENDING'
        SENT = 'SENT', 'SENT'
        FAILED = 'FAILED', 'FAILED'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='outbox_events')
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Outbox Event'
        verbose_name_plural = 'Outbox Events'
