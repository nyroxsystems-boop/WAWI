"""Background tasks (stubs for queue processing)."""

import logging
from io import StringIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone

from billing.models import Invoice
from outbox.models import OutboxEvent
from outbox.utils import mark_sent

logger = logging.getLogger('inventree')


def process_outbox():
    """Process pending outbox events (stub, mark as sent)."""
    pending = OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)[:100]
    for evt in pending:
        logger.info('Processing outbox event %s', evt.id)
        mark_sent(evt)


def nightly_invoice_export():
    """Export issued invoices to CSV under media/exports."""
    date_str = timezone.now().date().isoformat()
    buffer = StringIO()
    buffer.write('id,invoice_number,status,total,currency,issue_date,due_date\n')
    for inv in Invoice.objects.filter(status=Invoice.Status.ISSUED):
        buffer.write(
            f'{inv.id},{inv.invoice_number},{inv.status},{inv.total},'
            f'{inv.currency},{inv.issue_date},{inv.due_date}\n'
        )

    path = f'exports/invoices-{date_str}.csv'
    default_storage.save(path, ContentFile(buffer.getvalue()))
    logger.info('Invoice export written to %s', path)


def refresh_prices():
    """Placeholder for price refresh."""
    logger.info('Refreshing prices at %s', timezone.now())


def refresh_offers():
    """Placeholder for offer refresh."""
    logger.info('Refreshing offers at %s', timezone.now())


def regenerate_missing_pdfs():
    """Rebuild PDFs for issued invoices without a stored file."""
    missing = Invoice.objects.filter(
        status__in=[
            Invoice.Status.ISSUED,
            Invoice.Status.SENT,
            Invoice.Status.PAID,
        ]
    ).filter(Q(pdf_file__isnull=True) | Q(pdf_file=''))

    for inv in missing:
        inv.generate_pdf()
        inv.save(update_fields=['pdf_file'])
        logger.info('Regenerated PDF for invoice %s', inv.id)
