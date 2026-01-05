"""Worker stub to process a queued job synchronously."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from .models import Document, Job, WawiConfig

logger = logging.getLogger('inventree')


def run_job(job_id) -> Job:
    """Process a single job synchronously."""
    start_wall = timezone.now()
    with transaction.atomic():
        job = (
            Job.objects.select_for_update()
            .select_related('document', 'tenant')
            .filter(id=job_id)
            .first()
        )
        if not job:
            raise ValueError('Job not found')

        # Respect max retries before starting
        if job.retry_count >= job.max_retries:
            job.status = Job.Status.FAILED
            job.last_error = f'max retries reached ({job.retry_count}/{job.max_retries})'
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
            logger.warning(
                'wawitest.job.skip_max_retries',
                extra={
                    'tenant': getattr(job.tenant, 'slug', None),
                    'job_id': job.id,
                    'doc_id': getattr(job.document, 'id', None),
                },
            )
            return job

        job.status = Job.Status.RUNNING
        job.started_at = job.started_at or timezone.now()
        job.save(update_fields=['status', 'started_at', 'updated_at'])

    doc = job.document
    doc.last_attempt_at = timezone.now()
    doc.save(update_fields=['last_attempt_at', 'updated_at'])
    cfg = WawiConfig.objects.filter(tenant=job.tenant).first()
    logger.info(
        'wawitest.job.start',
        extra={'tenant': getattr(job.tenant, 'slug', None), 'job_id': job.id, 'doc_id': doc.id, 'status': job.status},
    )

    try:
        if not cfg or not cfg.is_active:
            raise RuntimeError('WawiConfig missing or inactive')

        # Simulate success
        doc.status = Document.Status.READY
        doc.last_error = ''
        doc.save(update_fields=['status', 'last_error', 'updated_at'])

        job.status = Job.Status.DONE
        job.last_error = ''
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
        logger.info(
            'wawitest.job.done',
            extra={
                'tenant': getattr(job.tenant, 'slug', None),
                'job_id': job.id,
                'doc_id': doc.id,
                'status': job.status,
                'duration_ms': int((job.finished_at - (job.started_at or start_wall)).total_seconds() * 1000),
            },
        )
        return job

    except Exception as exc:  # pragma: no cover - simple stub
        doc.status = Document.Status.FAILED
        doc.last_error = str(exc)
        doc.save(update_fields=['status', 'last_error', 'updated_at'])

        job.status = Job.Status.FAILED
        job.retry_count = (job.retry_count or 0) + 1
        job.last_error = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'retry_count', 'last_error', 'finished_at', 'updated_at'])
        logger.warning(
            'wawitest.job.failed',
            extra={
                'tenant': getattr(job.tenant, 'slug', None),
                'job_id': job.id,
                'doc_id': doc.id,
                'status': job.status,
                'duration_ms': int((job.finished_at - (job.started_at or start_wall)).total_seconds() * 1000),
                'error': job.last_error,
            },
        )
        return job
