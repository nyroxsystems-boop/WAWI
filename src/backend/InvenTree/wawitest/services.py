"""Service helpers for WAWI test document creation."""

from __future__ import annotations

import hashlib

from django.db import transaction
from django.utils import timezone

from tenancy.models import Tenant
from .models import Document, Job


def make_dedupe_key(tenant_id: int | str, order_id: str, doc_type: str, version: int) -> str:
    payload = f'{tenant_id}:{order_id}:{doc_type}:{version}'
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def request_document_create(
    tenant: Tenant,
    order_id: str,
    doc_type: str,
    version: int,
    created_by_user_id: int | None = None,
) -> tuple[Document, Job | None]:
    """Idempotently ensure a document + queued job exists for the tenant."""
    dedupe = make_dedupe_key(tenant.id, order_id, doc_type, version)

    with transaction.atomic():
        doc, _ = Document.objects.get_or_create(
            tenant=tenant,
            dedupe_key=dedupe,
            defaults={
                'order_id': order_id,
                'doc_type': doc_type,
                'version': version,
                'created_by_user_id': created_by_user_id,
                'status': Document.Status.CREATING,
            },
        )

        if doc.status == Document.Status.READY:
            existing = Job.objects.filter(tenant=tenant, document=doc).order_by('-created_at').first()
            return doc, existing

        if doc.status == Document.Status.FAILED:
            doc.status = Document.Status.CREATING
            doc.last_error = ''
            doc.save(update_fields=['status', 'last_error', 'updated_at'])

        existing_job = Job.objects.filter(tenant=tenant, document=doc, status__in=[Job.Status.QUEUED, Job.Status.RUNNING]).first()
        if existing_job:
            return doc, existing_job

        job = Job.objects.create(
            tenant=tenant,
            document=doc,
            status=Job.Status.QUEUED,
            retry_count=(doc.jobs.count() or 0) + 1,
        )
        doc.last_attempt_at = timezone.now()
        doc.save(update_fields=['last_attempt_at', 'updated_at'])
        return doc, job


def retry_document(tenant: Tenant, document_id: int) -> tuple[Document, Job | None]:
    """Retry a document: only enqueue if not already ready or running."""
    with transaction.atomic():
        doc = (
            Document.objects.select_for_update()
            .filter(tenant=tenant, id=document_id)
            .first()
        )
        if not doc:
            raise Document.DoesNotExist()

        if doc.status == Document.Status.READY:
            return doc, None

        if doc.status == Document.Status.FAILED:
            doc.status = Document.Status.CREATING
            doc.last_error = ''
            doc.save(update_fields=['status', 'last_error', 'updated_at'])

        existing_job = Job.objects.filter(
            tenant=tenant,
            document=doc,
            status__in=[Job.Status.QUEUED, Job.Status.RUNNING],
        ).first()
        if existing_job:
            return doc, existing_job

        job = Job.objects.create(
            tenant=tenant,
            document=doc,
            status=Job.Status.QUEUED,
            retry_count=(doc.jobs.count() or 0) + 1,
        )
        doc.last_attempt_at = timezone.now()
        doc.save(update_fields=['last_attempt_at', 'updated_at'])
        return doc, job
