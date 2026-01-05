"""DRF views for external sync endpoints."""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db import connection
from django.http import FileResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.permissions import IsTenantOrServiceToken

from .models import ExternalDocument, ExternalOrder, Job
from .serializers import ExternalDocumentCreateSerializer, ExternalOrderUpsertSerializer

logger = logging.getLogger('inventree')


def get_tenant(request):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return None
    return tenant


def require_idempotency_key(request) -> str | None:
    key = request.headers.get('Idempotency-Key')
    if key:
        return key.strip()
    return None


def build_order_state_response(request, order: ExternalOrder) -> dict:
    docs = []
    for d in order.documents.all().order_by('created_at'):
        docs.append({
            'id': str(d.id),
            'type': d.type,
            'status': d.status,
            'number': d.number,
            'error': d.error or None,
            'pdf_url': f"/api/ext/documents/{d.id}/pdf/",
        })

    return {
        'order_id': str(order.id),
        'status': order.status,
        'version': order.version,
        'documents': docs,
        'updated_at': order.updated_at.isoformat(),
    }


class ExternalOrderView(APIView):
    """PUT order upsert + GET status."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request, order_id: str):
        tenant = get_tenant(request)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        order = ExternalOrder.objects.filter(tenant=tenant, id=order_id).prefetch_related('documents').first()
        if order is None:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response(build_order_state_response(request, order))

    def put(self, request, order_id: str):
        tenant = get_tenant(request)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        idempotency_key = require_idempotency_key(request)
        if not idempotency_key:
            return Response({'detail': 'Idempotency-Key header required'}, status=status.HTTP_400_BAD_REQUEST)

        existing_job = Job.objects.filter(tenant=tenant, dedupe_key=idempotency_key).first()
        if existing_job:
            if existing_job.type != Job.JobType.UPSERT_ORDER:
                return Response(
                    {'detail': 'Idempotency-Key already used for a different operation'},
                    status=status.HTTP_409_CONFLICT,
                )
            if str(existing_job.payload.get('order_id')) not in [None, str(order_id)]:
                return Response(
                    {'detail': 'Idempotency-Key already used for a different order_id'},
                    status=status.HTTP_409_CONFLICT,
                )
            if existing_job.status == Job.Status.SUCCEEDED:
                order = ExternalOrder.objects.filter(tenant=tenant, id=order_id).prefetch_related('documents').first()
                if order is None:
                    return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
                return Response(build_order_state_response(request, order), status=status.HTTP_200_OK)
            if existing_job.status in [Job.Status.QUEUED, Job.Status.FAILED, Job.Status.RUNNING]:
                return Response(
                    {'ok': True, 'job_id': str(existing_job.id), 'order_id': str(order_id), 'status': existing_job.status},
                    status=status.HTTP_202_ACCEPTED,
                )
            return Response(
                {
                    'detail': 'Job failed; use a new Idempotency-Key to retry',
                    'job_id': str(existing_job.id),
                    'status': existing_job.status,
                    'error': existing_job.last_error,
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = ExternalOrderUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        incoming_version = int(validated.get('version') or 1)

        with transaction.atomic():
            order_qs = ExternalOrder.objects.filter(tenant=tenant, id=order_id)
            if connection.features.has_select_for_update:
                order_qs = order_qs.select_for_update()
            order = order_qs.first()
            if order and incoming_version < int(order.version):
                return Response({'detail': 'stale version'}, status=status.HTTP_409_CONFLICT)

            if not order:
                order = ExternalOrder(tenant=tenant, id=order_id)

            order.status = validated.get('status') or order.status
            order.version = incoming_version
            order.payload = validated
            order.save()

            try:
                job, created = Job.objects.get_or_create(
                    tenant=tenant,
                    dedupe_key=idempotency_key,
                    defaults={
                        'type': Job.JobType.UPSERT_ORDER,
                        'payload': {'order_id': str(order_id), 'version': incoming_version},
                        'status': Job.Status.QUEUED,
                    },
                )
            except IntegrityError:
                job = Job.objects.filter(tenant=tenant, dedupe_key=idempotency_key).first()
                created = False

            if not job:
                return Response({'detail': 'Failed to create job'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if not created:
                if job.type != Job.JobType.UPSERT_ORDER:
                    return Response(
                        {'detail': 'Idempotency-Key already used for a different operation'},
                        status=status.HTTP_409_CONFLICT,
                    )

                if job.status == Job.Status.SUCCEEDED:
                    return Response(build_order_state_response(request, order), status=status.HTTP_200_OK)
                return Response(
                    {'ok': True, 'job_id': str(job.id), 'order_id': str(order_id), 'status': job.status},
                    status=status.HTTP_202_ACCEPTED,
                )

        return Response(
            {'ok': True, 'job_id': str(job.id), 'order_id': str(order_id), 'status': Job.Status.QUEUED},
            status=status.HTTP_202_ACCEPTED,
        )


class ExternalDocumentCreateView(APIView):
    """POST create document for an order."""

    permission_classes = [IsTenantOrServiceToken]

    def post(self, request, order_id: str):
        tenant = get_tenant(request)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        idempotency_key = require_idempotency_key(request)
        if not idempotency_key:
            return Response({'detail': 'Idempotency-Key header required'}, status=status.HTTP_400_BAD_REQUEST)

        existing_job = Job.objects.filter(tenant=tenant, dedupe_key=idempotency_key).first()
        if existing_job:
            if existing_job.type != Job.JobType.GENERATE_DOCUMENT:
                return Response(
                    {'detail': 'Idempotency-Key already used for a different operation'},
                    status=status.HTTP_409_CONFLICT,
                )
            document_id = existing_job.payload.get('document_id')
            if existing_job.status == Job.Status.SUCCEEDED:
                doc = ExternalDocument.objects.filter(tenant=tenant, id=document_id).first()
                return Response(
                    {
                        'job_id': str(existing_job.id),
                        'document_id': str(document_id),
                        'status': doc.status if doc else existing_job.status,
                    },
                    status=status.HTTP_200_OK,
                )
            if existing_job.status in [Job.Status.QUEUED, Job.Status.FAILED, Job.Status.RUNNING]:
                return Response(
                    {
                        'job_id': str(existing_job.id),
                        'document_id': str(document_id),
                        'status': existing_job.status,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            return Response(
                {
                    'detail': 'Job failed; use a new Idempotency-Key to retry',
                    'job_id': str(existing_job.id),
                    'status': existing_job.status,
                    'error': existing_job.last_error,
                },
                status=status.HTTP_409_CONFLICT,
            )

        order = ExternalOrder.objects.filter(tenant=tenant, id=order_id).first()
        if not order:
            return Response({'detail': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExternalDocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc_type = serializer.validated_data['type']

        with transaction.atomic():
            try:
                job, created = Job.objects.get_or_create(
                    tenant=tenant,
                    dedupe_key=idempotency_key,
                    defaults={
                        'type': Job.JobType.GENERATE_DOCUMENT,
                        'payload': {'order_id': str(order_id), 'type': doc_type},
                        'status': Job.Status.QUEUED,
                    },
                )
            except IntegrityError:
                job = Job.objects.filter(tenant=tenant, dedupe_key=idempotency_key).first()
                created = False

            if not job:
                return Response({'detail': 'Failed to create job'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            if not created:
                if job.type != Job.JobType.GENERATE_DOCUMENT:
                    return Response(
                        {'detail': 'Idempotency-Key already used for a different operation'},
                        status=status.HTTP_409_CONFLICT,
                    )
                document_id = job.payload.get('document_id')
                return Response(
                    {'job_id': str(job.id), 'document_id': str(document_id), 'status': job.status},
                    status=status.HTTP_202_ACCEPTED,
                )

            # Create document only when we created the job (idempotent)
            doc = ExternalDocument.objects.create(
                tenant=tenant,
                order=order,
                type=doc_type,
                status=ExternalDocument.Status.CREATING,
            )
            job.payload = {'order_id': str(order_id), 'type': doc_type, 'document_id': str(doc.id)}
            job.save(update_fields=['payload'])

        return Response(
            {'job_id': str(job.id), 'document_id': str(doc.id), 'status': Job.Status.QUEUED},
            status=status.HTTP_202_ACCEPTED,
        )


class ExternalDocumentPdfView(APIView):
    """GET download document PDF."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request, document_id: str):
        tenant = get_tenant(request)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        doc = ExternalDocument.objects.filter(tenant=tenant, id=document_id).select_related('order').first()
        if not doc:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if doc.status != ExternalDocument.Status.READY or not doc.pdf_file:
            return Response({'detail': 'Document not ready'}, status=status.HTTP_409_CONFLICT)

        file_handle = doc.pdf_file.open('rb')
        filename = f"{doc.type.lower()}-{doc.number or doc.id}.pdf"
        return FileResponse(file_handle, content_type='application/pdf', as_attachment=True, filename=filename)


class JobStatusView(APIView):
    """GET status of a queued job (tenant-scoped)."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request, job_id: str):
        tenant = get_tenant(request)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        job = Job.objects.filter(tenant=tenant, id=job_id).first()
        if job is None:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                'id': str(job.id),
                'type': job.type,
                'status': job.status,
                'attempts': job.attempts,
                'max_attempts': job.max_attempts,
                'run_at': job.run_at.isoformat() if job.run_at else None,
                'last_error': job.last_error or '',
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'updated_at': job.updated_at.isoformat() if job.updated_at else None,
            }
        )
