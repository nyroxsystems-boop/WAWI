"""API endpoints for billing."""

import csv
from io import StringIO

from django.http import HttpResponse
from django.urls import include, path
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from billing.models_settings import BillingSettings
from tenancy.permissions import IsTenantOrServiceToken
from .models import Invoice
from .serializers import InvoiceSerializer


class InvoiceViewSet(viewsets.ModelViewSet):
    """CRUD for invoices plus actions."""

    permission_classes = [IsTenantOrServiceToken]
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.select_related('contact', 'order')
    pagination_class = None
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        qs = self.queryset
        if tenant:
            qs = qs.filter(tenant=tenant)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_context(self):
        """Inject tenant into serializer context."""
        ctx = super().get_serializer_context()
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

    def perform_create(self, serializer):
        serializer.save(tenant=getattr(self.request, 'tenant', None))

    @action(detail=True, methods=['post'])
    def issue(self, request, pk=None):
        invoice = self.get_object()
        try:
            invoice.issue()
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from audit.utils import log_audit
        log_audit('INVOICE_ISSUED', tenant=invoice.tenant, actor=getattr(request, 'user', None), metadata={'invoice_id': invoice.id})
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        invoice = self.get_object()
        try:
            invoice.send()
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        try:
            invoice.mark_paid()
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        invoice = self.get_object()
        try:
            invoice.cancel()
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from audit.utils import log_audit
        log_audit('INVOICE_CANCELED', tenant=invoice.tenant, actor=getattr(request, 'user', None), metadata={'invoice_id': invoice.id})
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=['get'], url_path='pdf')
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        if not invoice.pdf_file:
            try:
                invoice.generate_pdf()
                invoice.save(update_fields=['pdf_file'])
            except Exception as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(
            invoice.pdf_file.open('rb').read(),
            content_type='application/pdf',
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{invoice.invoice_number or invoice.id}.pdf"'
        )
        return response


class BillingSettingsViewSet(viewsets.ViewSet):
    """Get/Update billing settings per tenant."""

    permission_classes = [IsTenantOrServiceToken]

    def retrieve(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)
        settings_obj, _ = BillingSettings.objects.get_or_create(
            tenant=tenant,
            defaults={
                'company_name': tenant.name,
                'address_line1': '',
                'city': '',
                'postal_code': '',
            },
        )
        return Response({
            'company_name': settings_obj.company_name,
            'address_line1': settings_obj.address_line1,
            'address_line2': settings_obj.address_line2,
            'city': settings_obj.city,
            'postal_code': settings_obj.postal_code,
            'country': settings_obj.country,
            'tax_id': settings_obj.tax_id,
            'iban': settings_obj.iban,
            'email': settings_obj.email,
            'phone': settings_obj.phone,
        })

    def update(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)
        settings_obj, _ = BillingSettings.objects.get_or_create(
            tenant=tenant,
            defaults={'company_name': tenant.name, 'address_line1': '', 'city': '', 'postal_code': ''},
        )
        for field in [
            'company_name',
            'address_line1',
            'address_line2',
            'city',
            'postal_code',
            'country',
            'tax_id',
            'iban',
            'email',
            'phone',
        ]:
            if field in request.data:
                setattr(settings_obj, field, request.data[field])
        settings_obj.save()
        from audit.utils import log_audit
        log_audit('BILLING_SETTINGS_UPDATED', tenant=tenant, actor=getattr(request, 'user', None))
        return Response({'detail': 'updated'})


class InvoiceExportView(viewsets.ViewSet):
    """Export invoices to CSV."""

    permission_classes = [IsTenantOrServiceToken]

    def list(self, request):
        tenant = getattr(request, 'tenant', None)
        qs = Invoice.objects.filter(tenant=tenant) if tenant else Invoice.objects.none()
        start = request.query_params.get('from')
        end = request.query_params.get('to')
        if start:
            qs = qs.filter(issue_date__gte=start)
        if end:
            qs = qs.filter(issue_date__lte=end)

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            'id',
            'invoice_number',
            'status',
            'total',
            'currency',
            'issue_date',
            'due_date',
            'order_id',
            'contact_id',
        ])
        for inv in qs:
            writer.writerow([
                inv.id,
                inv.invoice_number,
                inv.status,
                inv.total,
                inv.currency,
                inv.issue_date,
                inv.due_date,
                inv.order_id,
                inv.contact_id,
            ])

        resp = HttpResponse(buffer.getvalue(), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="invoices.csv"'
        return resp


router = DefaultRouter()
router.trailing_slash = '/?'
router.register('invoices', InvoiceViewSet, basename='billing-invoices')
router.register('reports/invoices/export', InvoiceExportView, basename='billing-invoices-export')
router.register('settings/billing', BillingSettingsViewSet, basename='billing-settings')

api_urls = [path('', include(router.urls))]
