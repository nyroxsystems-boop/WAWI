"""Simple polling worker to process queued wawitest jobs."""

from __future__ import annotations

import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from wawitest.models import Job
from wawitest.worker import run_job

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run wawitest job worker (polling, SKIP LOCKED).'

    def add_arguments(self, parser):
        parser.add_argument('--sleep-ms', type=int, default=500, help='Sleep between loops when idle (ms)')
        parser.add_argument('--max-jobs-per-loop', type=int, default=10, help='Max jobs to fetch per loop')

    def handle(self, *args, **options):
        sleep_ms = max(options['sleep_ms'], 10)
        batch_size = max(options['max_jobs_per_loop'], 1)
        running = True

        def _stop(*_args):
            nonlocal running
            running = False
            logger.info('wawitest.worker.stop_requested')

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        logger.info('wawitest.worker.start', extra={'sleep_ms': sleep_ms, 'batch_size': batch_size})

        while running:
            job_ids = []
            now = timezone.now()
            with transaction.atomic():
                jobs = (
                    Job.objects.select_for_update(skip_locked=True)
                    .select_related('tenant', 'document')
                    .filter(status=Job.Status.QUEUED)
                    .order_by('created_at')[:batch_size]
                )

                for job in jobs:
                    if job.retry_count >= job.max_retries:
                        job.status = Job.Status.FAILED
                        job.last_error = f'max retries reached ({job.retry_count}/{job.max_retries})'
                        job.finished_at = now
                        job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
                        logger.warning(
                            'wawitest.worker.skip_max_retries',
                            extra={'tenant': getattr(job.tenant, 'slug', None), 'job_id': job.id},
                        )
                        continue

                    job.status = Job.Status.RUNNING
                    job.started_at = job.started_at or now
                    job.save(update_fields=['status', 'started_at', 'updated_at'])
                    job_ids.append(job.id)

            if not job_ids:
                time.sleep(sleep_ms / 1000.0)
                continue

            for jid in job_ids:
                try:
                    run_job(jid)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception('wawitest.worker.run_job_error', extra={'job_id': jid, 'error': str(exc)})

        logger.info('wawitest.worker.exit')
