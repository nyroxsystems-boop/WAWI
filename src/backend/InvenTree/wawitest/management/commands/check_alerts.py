"""Simple alert checker for stuck/failed wawitest jobs."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from wawitest.models import Document, Job

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check for failed jobs or stuck documents; exit 2 on alert.'

    def add_arguments(self, parser):
        parser.add_argument('--stuck-minutes', type=int, default=10, help='Minutes after which creating docs count as stuck')

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=options['stuck_minutes'])

        jobs_failed = Job.objects.filter(status=Job.Status.FAILED).count()
        docs_stuck = Document.objects.filter(status=Document.Status.CREATING, updated_at__lt=cutoff).count()

        if jobs_failed > 0 or docs_stuck > 0:
            logger.warning(
                'wawitest.alert',
                extra={
                    'jobs_failed': jobs_failed,
                    'docs_stuck_creating': docs_stuck,
                    'stuck_minutes': options['stuck_minutes'],
                },
            )
            self.stdout.write(self.style.WARNING(f'Alerts: jobs_failed={jobs_failed}, docs_stuck={docs_stuck}'))
            raise SystemExit(2)

        self.stdout.write('No alerts')
        raise SystemExit(0)
