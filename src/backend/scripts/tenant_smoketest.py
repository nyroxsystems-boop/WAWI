"""Minimal smoketest for tenant + wawitest workflow."""

import os
import sys

import django


def setup_django():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base_dir, '..', 'InvenTree'))
    sys.path.append(project_root)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'InvenTree.settings')
    django.setup()


def main():
    setup_django()

    from tenancy.models import Tenant, TenantUser  # noqa: E402
    from users.models import User  # noqa: E402
    from wawitest.models import Document, Job, WawiConfig  # noqa: E402
    from wawitest.services import request_document_create  # noqa: E402
    from wawitest.worker import run_job  # noqa: E402

    tenant, _ = Tenant.objects.get_or_create(slug='smoketest', defaults={'name': 'Smoketest', 'status': 'active', 'is_active': True})

    user, _ = User.objects.get_or_create(email='smoke@example.com', defaults={'username': 'smoke@example.com'})
    if not user.has_usable_password():
        user.set_password('smokepass')
        user.save()

    TenantUser.objects.update_or_create(tenant=tenant, user=user, defaults={'role': TenantUser.Role.TENANT_ADMIN, 'is_active': True})

    WawiConfig.objects.update_or_create(tenant=tenant, defaults={'base_url': 'https://example.com', 'api_token': 'token', 'is_active': True})

    doc, job = request_document_create(tenant=tenant, order_id='SMOKE-1', doc_type='invoice', version=1, created_by_user_id=user.id)
    if job:
        run_job(job.id)

    doc.refresh_from_db()
    last_job = Job.objects.filter(tenant=tenant, document=doc).order_by('-created_at').first()

    assert doc.status == Document.Status.READY, f'Document not ready: {doc.status}'
    assert last_job and last_job.status == Job.Status.DONE, f'Job not done: {getattr(last_job, \"status\", None)}'
    print('Smoketest OK: document ready, job done')


if __name__ == '__main__':
    main()
