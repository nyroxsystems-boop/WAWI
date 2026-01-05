"""Dashboard-style test views for tenant-scoped WAWI docs/jobs."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token

from tenancy.authz import require_role, require_tenant
from tenancy.models import TenantUser
from .models import Document, Job
from .services import request_document_create
from .worker import run_job


def _role_alias(role: str | None) -> str:
    if not role:
        return 'none'
    if role == TenantUser.Role.OWNER_ADMIN:
        return 'owner'
    if role == TenantUser.Role.TENANT_ADMIN:
        return 'staff'
    if role == TenantUser.Role.TENANT_USER:
        return 'readonly'
    return str(role).lower()


@require_tenant
def dashboard_home(request):
    tenant = request.tenant
    tenant_user = getattr(request, 'tenant_user', None)
    role_alias = _role_alias(getattr(tenant_user, 'role', None))
    can_manage = role_alias in ['staff', 'owner']

    docs = Document.objects.filter(tenant=tenant).order_by('-created_at')[:100]
    jobs = Job.objects.filter(tenant=tenant).select_related('document').order_by('-created_at')[:100]

    return render(
        request,
        'wawitest/dashboard.html',
        {
            'tenant': tenant,
            'tenant_user': tenant_user,
            'role_alias': role_alias,
            'can_manage': can_manage,
            'documents': docs,
            'jobs': jobs,
        },
    )


@require_http_methods(['POST'])
@require_role('staff')
def create_document(request):
    tenant = request.tenant
    order_id = request.POST.get('order_id') or ''
    doc_type = request.POST.get('doc_type') or 'invoice'
    version = int(request.POST.get('version') or 1)

    doc, job = request_document_create(
        tenant=tenant,
        order_id=order_id,
        doc_type=doc_type,
        version=version,
        created_by_user_id=getattr(request.user, 'id', None),
    )
    if job:
        messages.success(request, f'Document {doc.id} queued (job {job.id})')
    else:
        messages.info(request, f'Document {doc.id} already ready; kein neuer Job erstellt.')
    return redirect('wawitest:dashboard')


@require_http_methods(['POST'])
@require_role('staff')
def retry_document(request, document_id: int):
    tenant = request.tenant
    doc = get_object_or_404(Document, tenant=tenant, id=document_id)
    # Fixed: Import and call the service function correctly
    doc, job = request_document_create(
        tenant=tenant,
        order_id=doc.order_id,
        doc_type=doc.doc_type,
        version=doc.version + 1,
        created_by_user_id=getattr(request.user, 'id', None),
    )
    if job:
        messages.success(request, f'Retry queued (job {job.id})')
    else:
        messages.info(request, 'Kein neuer Job (Dokument evtl. schon ready oder laufender Job).')
    return redirect('wawitest:dashboard')


@require_http_methods(['POST'])
@require_role('staff')
def force_fail(request, document_id: int):
    tenant = request.tenant
    doc = get_object_or_404(Document, tenant=tenant, id=document_id)
    doc.status = Document.Status.FAILED
    doc.last_error = 'FORCED FAIL (test button)'
    doc.save(update_fields=['status', 'last_error', 'updated_at'])
    messages.error(request, f'Document {doc.id} marked as failed.')
    return redirect('wawitest:dashboard')


@require_http_methods(['POST'])
@require_role('staff')
def run_one(request):
    tenant = request.tenant
    job = Job.objects.filter(tenant=tenant, status=Job.Status.QUEUED).order_by('created_at').first()
    if not job:
        messages.info(request, 'No queued job to run.')
        return redirect('wawitest:dashboard')

    run_job(job.id)
    messages.success(request, f'Job {job.id} processed.')
    return redirect('wawitest:dashboard')


@csrf_exempt
@require_http_methods(['GET', 'OPTIONS'])
def bot_health(request):
    """Simple liveness endpoint for dashboard pings."""
    return JsonResponse({'status': 'ok'})


@csrf_exempt
@require_http_methods(['GET', 'OPTIONS'])
def dashboard_orders(request):
    """Placeholder orders endpoint to keep dashboard functional."""
    return JsonResponse([], safe=False)
