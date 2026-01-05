"""Tenant-scoped test models for WAWI document creation."""

from __future__ import annotations

from django.db import models

from tenancy.models import Tenant


class TenantScopedModel(models.Model):
    """Abstract base for tenant-scoped entities."""

    class Meta:
        abstract = True


class Document(TenantScopedModel):
    """Simplified document representation for testing WAWI integration."""

    class Status(models.TextChoices):
        CREATING = 'creating', 'creating'
        READY = 'ready', 'ready'
        FAILED = 'failed', 'failed'

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='wawitest_documents',
        related_query_name='wawitest_document',
    )
    order_id = models.CharField(max_length=100, db_index=True)
    doc_type = models.CharField(max_length=50)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATING)
    dedupe_key = models.CharField(max_length=128, blank=True, null=True, db_index=True, unique=False)
    last_error = models.TextField(blank=True, default='')
    created_by_user_id = models.IntegerField(blank=True, null=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'order_id', 'doc_type', 'version'], name='uniq_doc_order_type_version'),
            models.UniqueConstraint(fields=['tenant', 'dedupe_key'], name='uniq_doc_dedupe_per_tenant', condition=models.Q(dedupe_key__isnull=False)),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order_id} {self.doc_type} v{self.version} ({self.status})'


class Job(TenantScopedModel):
    """Queued job for document processing."""

    class Status(models.TextChoices):
        QUEUED = 'queued', 'queued'
        RUNNING = 'running', 'running'
        DONE = 'done', 'done'
        FAILED = 'failed', 'failed'

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='wawitest_jobs',
        related_query_name='wawitest_job',
    )
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='jobs')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    last_error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Job {self.id} ({self.status})'


class WawiConfig(models.Model):
    """Per-tenant WAWI configuration (stub for testing)."""

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='wawi_config')
    base_url = models.CharField(max_length=255, blank=True, default='')
    api_token = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'WawiConfig({self.tenant.slug})'
