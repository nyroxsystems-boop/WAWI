"""Management command to process outbox events."""

from django.core.management.base import BaseCommand

from outbox.tasks import process_outbox


class Command(BaseCommand):
    """Process pending outbox events (stub)."""

    help = 'Process pending outbox events'

    def handle(self, *args, **options):
        process_outbox()
        self.stdout.write(self.style.SUCCESS('Processed outbox events'))
