"""Models for dashboard -> WWS external sync workflow.

This app provides:
- ExternalOrder / ExternalDocument storage
- A DB-backed job queue for async processing on Render (no Redis required)
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from tenancy.models import TenantScopedModel


class ExternalOrder(TenantScopedModel):
    """Order payload received from the dashboard (external system)."""

    # Stable external id from dashboard (tenant-scoped by request.tenant)
    id = models.CharField(max_length=100, primary_key=True)

    status = models.CharField(max_length=64, default='')
    version = models.PositiveIntegerField(default=1)
    payload = models.JSONField(default=dict, blank=True)

    wws_order_no = models.CharField(max_length=64, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'External Order'
        verbose_name_plural = 'External Orders'
        indexes = [
            models.Index(fields=['tenant', 'updated_at'], name='extsync_ord_tenant_upd_idx'),
        ]

    def __str__(self) -> str:
        return f'ExternalOrder {self.id} (tenant={self.tenant_id})'


class ExternalDocument(TenantScopedModel):
    """Document generated in WWS for an ExternalOrder (quote/invoice)."""

    class DocumentType(models.TextChoices):
        QUOTE = 'QUOTE', 'QUOTE'
        INVOICE = 'INVOICE', 'INVOICE'

    class Status(models.TextChoices):
        CREATING = 'creating', 'creating'
        READY = 'ready', 'ready'
        FAILED = 'failed', 'failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        ExternalOrder, on_delete=models.CASCADE, related_name='documents', db_index=True
    )
    type = models.CharField(max_length=16, choices=DocumentType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATING)

    number = models.CharField(max_length=64, null=True, blank=True)
    # Stored in MEDIA_ROOT / configured storage. On Render the local disk is ephemeral,
    # so production deployments should point MEDIA storage to a durable backend (e.g. S3).
    pdf_file = models.FileField(upload_to='extsync/documents/', null=True, blank=True)
    error = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'External Document'
        verbose_name_plural = 'External Documents'
        indexes = [
            models.Index(fields=['tenant', 'status'], name='extsync_doc_tenant_stat_idx'),
            models.Index(fields=['tenant', 'order'], name='extsync_doc_tenant_ord_idx'),
        ]

    def __str__(self) -> str:
        return f'ExternalDocument {self.id} ({self.type})'


class Job(TenantScopedModel):
    """DB-backed job queue entry."""

    class JobType(models.TextChoices):
        UPSERT_ORDER = 'UPSERT_ORDER', 'UPSERT_ORDER'
        GENERATE_DOCUMENT = 'GENERATE_DOCUMENT', 'GENERATE_DOCUMENT'

    class Status(models.TextChoices):
        QUEUED = 'queued', 'queued'
        RUNNING = 'running', 'running'
        SUCCEEDED = 'succeeded', 'succeeded'
        FAILED = 'failed', 'failed'
        DEAD = 'dead', 'dead'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=32, choices=JobType.choices)
    dedupe_key = models.CharField(max_length=128)
    payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=8)

    run_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Job'
        verbose_name_plural = 'Jobs'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'dedupe_key'], name='uniq_job_dedupe_tenant'),
        ]
        indexes = [
            models.Index(fields=['status', 'run_at'], name='extsync_job_stat_run_idx'),
        ]

    def __str__(self) -> str:
        return f'Job {self.id} {self.type} ({self.status})'


class NumberSequence(TenantScopedModel):
    """Simple per-tenant sequence used for ExternalDocument numbering."""

    name = models.CharField(max_length=32)
    current = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Number Sequence'
        verbose_name_plural = 'Number Sequences'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'name'], name='uniq_sequence_tenant_name'),
        ]

    def __str__(self) -> str:
        return f'NumberSequence {self.name}={self.current}'
