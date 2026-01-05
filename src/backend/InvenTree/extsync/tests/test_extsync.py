"""Tests for external sync endpoints and worker."""

from __future__ import annotations

import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.models import Tenant, TenantUser


class ExtSyncTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='extsync', email='extsync@example.com', password='pass123'
        )
        self.tenant = Tenant.objects.create(name='ExtTenant', slug='ext-tenant')
        TenantUser.objects.create(
            user=self.user, tenant=self.tenant, role='TENANT_ADMIN', is_active=True
        )

        token = AccessToken.for_user(self.user)
        token['tenant_id'] = self.tenant.id
        token['role'] = 'TENANT_ADMIN'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')

    def test_order_upsert_idempotency(self):
        payload = {
            'status': 'READY_FOR_WWS',
            'version': 3,
            'customer': {'name': 'Max Mustermann', 'phone': '+49', 'email': 'max@example.com'},
            'lines': [{'sku': 'SKU123', 'oe_number': 'OE', 'name': 'Part', 'qty': 1, 'unit_price': 99.0, 'tax_rate': 19}],
            'notes': 'hello',
        }

        resp1 = self.client.put(
            '/api/ext/orders/order-1/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='key-1',
        )
        self.assertEqual(resp1.status_code, 202)
        job_id_1 = resp1.json()['job_id']

        job_resp = self.client.get(f'/api/ext/jobs/{job_id_1}/')
        self.assertEqual(job_resp.status_code, 200)
        self.assertEqual(job_resp.json()['id'], job_id_1)
        self.assertEqual(job_resp.json()['type'], 'UPSERT_ORDER')
        self.assertIn(job_resp.json()['status'], ['queued', 'running', 'failed'])

        resp2 = self.client.put(
            '/api/ext/orders/order-1/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='key-1',
        )
        self.assertEqual(resp2.status_code, 202)
        self.assertEqual(resp2.json()['job_id'], job_id_1)

        # Process queued jobs
        call_command('run_jobs', once=True, sleep=0)

        job_resp2 = self.client.get(f'/api/ext/jobs/{job_id_1}/')
        self.assertEqual(job_resp2.status_code, 200)
        self.assertEqual(job_resp2.json()['status'], 'succeeded')

        resp3 = self.client.put(
            '/api/ext/orders/order-1/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='key-1',
        )
        self.assertEqual(resp3.status_code, 200)
        self.assertEqual(resp3.json()['order_id'], 'order-1')
        self.assertEqual(resp3.json()['version'], 3)

    def test_document_generation_and_pdf_download(self):
        order_payload = {
            'status': 'READY_FOR_WWS',
            'version': 1,
            'customer': {'name': 'Test', 'phone': '+49', 'email': 't@example.com'},
            'lines': [{'sku': 'SKU', 'oe_number': 'OE', 'name': 'Part', 'qty': 1, 'unit_price': 10.0, 'tax_rate': 0}],
        }
        self.client.put(
            '/api/ext/orders/order-doc/',
            order_payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='upsert-doc',
        )

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=tmp):
                resp1 = self.client.post(
                    '/api/ext/orders/order-doc/documents/',
                    {'type': 'INVOICE'},
                    format='json',
                    HTTP_IDEMPOTENCY_KEY='doc-key-1',
                )
                self.assertEqual(resp1.status_code, 202)
                document_id = resp1.json()['document_id']
                job_id = resp1.json()['job_id']

                resp2 = self.client.post(
                    '/api/ext/orders/order-doc/documents/',
                    {'type': 'INVOICE'},
                    format='json',
                    HTTP_IDEMPOTENCY_KEY='doc-key-1',
                )
                self.assertEqual(resp2.status_code, 202)
                self.assertEqual(resp2.json()['document_id'], document_id)
                self.assertEqual(resp2.json()['job_id'], job_id)

                # Render PDF deterministically for tests (don't depend on system WeasyPrint libs)
                with patch(
                    'extsync.management.commands.run_jobs._render_document_pdf_bytes',
                    return_value=b'%PDF-1.4 test',
                ):
                    call_command('run_jobs', once=True, sleep=0)

                status_resp = self.client.get('/api/ext/orders/order-doc/')
                self.assertEqual(status_resp.status_code, 200)
                docs = status_resp.json().get('documents') or []
                self.assertTrue(len(docs) >= 1)

                pdf_resp = self.client.get(f'/api/ext/documents/{document_id}/pdf/')
                self.assertEqual(pdf_resp.status_code, 200)
                content = b''.join(pdf_resp.streaming_content)
                self.assertTrue(len(content) > 10)

    def test_document_failure_marks_failed(self):
        order_payload = {
            'status': 'READY_FOR_WWS',
            'version': 1,
            'customer': {'name': 'Test', 'phone': '+49', 'email': 't@example.com'},
            'lines': [{'sku': 'SKU', 'oe_number': 'OE', 'name': 'Part', 'qty': 1, 'unit_price': 10.0, 'tax_rate': 0}],
        }
        self.client.put(
            '/api/ext/orders/order-fail/',
            order_payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='upsert-fail',
        )

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=tmp):
                resp = self.client.post(
                    '/api/ext/orders/order-fail/documents/',
                    {'type': 'INVOICE'},
                    format='json',
                    HTTP_IDEMPOTENCY_KEY='doc-fail-1',
                )
                self.assertEqual(resp.status_code, 202)
                job_id = resp.json()['job_id']
                document_id = resp.json()['document_id']

                from extsync.models import Job
                Job.objects.filter(id=job_id).update(max_attempts=1)

                from extsync.management.commands import run_jobs as run_jobs_module
                with patch(
                    'extsync.management.commands.run_jobs._render_document_pdf_bytes',
                    side_effect=run_jobs_module.NonRetryableJobError('WeasyPrint missing'),
                ):
                    call_command('run_jobs', once=True, sleep=0)

                job_resp = self.client.get(f'/api/ext/jobs/{job_id}/')
                self.assertEqual(job_resp.status_code, 200)
                self.assertEqual(job_resp.json()['status'], 'dead')
                self.assertIn('WeasyPrint missing', job_resp.json()['last_error'])

                status_resp = self.client.get('/api/ext/orders/order-fail/')
                self.assertEqual(status_resp.status_code, 200)
                docs = status_resp.json().get('documents') or []
                doc = next((d for d in docs if d.get('id') == document_id), None)
                self.assertIsNotNone(doc)
                self.assertEqual(doc['status'], 'failed')
                self.assertIn('WeasyPrint missing', doc.get('error') or '')

                pdf_resp = self.client.get(f'/api/ext/documents/{document_id}/pdf/')
                self.assertEqual(pdf_resp.status_code, 409)
