"""Repair stuck jobs/documents for wawitest."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from wawitest.models import Document, Job

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Repair stuck wawitest jobs/documents'

    def add_arguments(self, parser):
        parser.add_argument('--stuck-minutes', type=int, default=30)
        parser.add_argument('--mode', choices=['requeue', 'fail'], default='requeue')

    def handle(self, *args, **options):
        stuck_minutes = options['stuck_minutes']
        mode = options['mode']
        cutoff = timezone.now() - timedelta(minutes=stuck_minutes)

        changed = False

        try:
            jobs = Job.objects.filter(status=Job.Status.RUNNING, started_at__lt=cutoff)
            docs = Document.objects.filter(status=Document.Status.CREATING, updated_at__lt=cutoff)

            for job in jobs:
                action = 'queued' if mode == 'requeue' else 'failed'
                logger.warning(
                    'repair.job',
                    extra={'tenant': getattr(job.tenant, 'slug', None), 'job_id': job.id, 'action': action},
                )
                if mode == 'requeue':
                    job.status = Job.Status.QUEUED
                    job.retry_count = (job.retry_count or 0) + 1
                    job.last_error = ''
                else:
                    job.status = Job.Status.FAILED
                    job.last_error = f'stuck > {stuck_minutes} min'
                job.save(update_fields=['status', 'retry_count', 'last_error', 'updated_at'])
                changed = True

            for doc in docs:
                action = 'creating' if mode == 'requeue' else 'failed'
                logger.warning(
                    'repair.doc',
                    extra={'tenant': getattr(doc.tenant, 'slug', None), 'doc_id': doc.id, 'action': action},
                )
                if mode == 'requeue':
                    doc.status = Document.Status.CREATING
                    doc.last_error = ''
                else:
                    doc.status = Document.Status.FAILED
                    doc.last_error = f'stuck > {stuck_minutes} min'
                doc.save(update_fields=['status', 'last_error', 'updated_at'])
                changed = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception('repair_jobs failed: %s', exc)
            self.stderr.write(self.style.ERROR(f'Error: {exc}'))
            raise SystemExit(2)

        if changed:
            self.stdout.write(self.style.SUCCESS('Repaired stuck records'))
            raise SystemExit(1)

        self.stdout.write('Nothing to repair')
        raise SystemExit(0)
