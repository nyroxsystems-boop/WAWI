"""Helpers to enqueue outbox events."""

from django.utils import timezone

from outbox.models import OutboxEvent


def create_event(event_type: str, tenant, payload: dict | None = None) -> OutboxEvent:
    """Create a pending event."""
    return OutboxEvent.objects.create(
        tenant=tenant, event_type=event_type, payload=payload or {}
    )


def mark_sent(event: OutboxEvent):
    """Mark event as sent."""
    event.status = OutboxEvent.Status.SENT
    event.sent_at = timezone.now()
    event.save(update_fields=['status', 'sent_at'])
