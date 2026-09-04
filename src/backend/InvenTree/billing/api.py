"""API endpoints for billing."""

import csv
from io import StringIO

from django.http import HttpResponse
from django.urls import include, path
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from billing.models_settings import BillingSettings
from tenancy.models import TenantUser
from tenancy.permissions import IsTenantOrServiceToken
from .models import Invoice
from .serializers import InvoiceSerializer


class BillingPagination(PageNumberPagination):
    """Pagination for billing endpoints."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class InvoiceViewSet(viewsets.ModelViewSet):
    """CRUD for invoices plus actions."""

    permission_classes = [IsTenantOrServiceToken]
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.select_related('contact', 'order')
    pagination_class = BillingPagination
    tenant_read_roles = {
        TenantUser.Role.TENANT_ADMIN,
        TenantUser.Role.OWNER_ADMIN,
    }
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if tenant is None:
            return self.queryset.none()
        qs = self.queryset.filter(tenant=tenant)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        order_filter = self.request.query_params.get('order')
        if order_filter:
            qs = qs.filter(order_id=order_filter)
        return qs

    def get_serializer_context(self):
        """Inject tenant into serializer context."""
        ctx = super().get_serializer_context()
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

    def perform_create(self, serializer):
        serializer.save(tenant=getattr(self.request, 'tenant', None))

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        """Create invoices for multiple orders at once."""
        from wws.models import Order
        from billing.models import InvoiceLine
        from decimal import Decimal

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        order_ids = request.data.get('orderIds', [])
        success = []
        failed = []

        for oid in order_ids:
            try:
                order = Order.objects.filter(tenant=tenant, id=oid).first()
                if not order:
                    failed.append({'orderId': str(oid), 'error': 'Order not found'})
                    continue

                invoice = Invoice.objects.create(
                    tenant=tenant,
                    order=order,
                    contact=order.contact,
                    currency=order.currency or 'EUR',
                    status='DRAFT',
                )
                unit_price = order.total_price if order.total_price else Decimal('0')
                InvoiceLine.objects.create(
                    tenant=tenant,
                    invoice=invoice,
                    description=order.oem or f'Order {order.id}',
                    quantity=1,
                    unit_price=unit_price,
                    tax_rate=0,
                )
                invoice.recalculate_totals()
                invoice.save()
                success.append(InvoiceSerializer(invoice).data)
            except Exception as e:
                failed.append({'orderId': str(oid), 'error': str(e)})

        return Response({'success': success, 'failed': failed})

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
    tenant_read_roles = {
        TenantUser.Role.TENANT_ADMIN,
        TenantUser.Role.OWNER_ADMIN,
    }

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
            'invoice_template': settings_obj.invoice_template,
            'invoice_color': settings_obj.invoice_color,
            'invoice_font': settings_obj.invoice_font,
            'logo_position': settings_obj.logo_position,
            'number_position': settings_obj.number_position,
            'address_layout': settings_obj.address_layout,
            'table_style': settings_obj.table_style,
            'accent_color': settings_obj.accent_color,
            'logo_base64': settings_obj.logo_base64,
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
            'invoice_template',
            'invoice_color',
            'invoice_font',
            'logo_position',
            'number_position',
            'address_layout',
            'table_style',
            'accent_color',
            'logo_base64',
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
    tenant_read_roles = {
        TenantUser.Role.TENANT_ADMIN,
        TenantUser.Role.OWNER_ADMIN,
    }

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
            'id', 'invoice_number', 'invoice_type', 'status', 'total',
            'currency', 'issue_date', 'due_date', 'order_id', 'contact_id',
        ])
        for inv in qs:
            writer.writerow([
                inv.id, inv.invoice_number, inv.invoice_type, inv.status,
                inv.total, inv.currency, inv.issue_date, inv.due_date,
                inv.order_id, inv.contact_id,
            ])

        resp = HttpResponse(buffer.getvalue(), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="invoices.csv"'
        return resp


class DATEVExportView(viewsets.ViewSet):
    """Export invoices in DATEV Buchungsstapel format."""

    permission_classes = [IsTenantOrServiceToken]
    tenant_read_roles = {
        TenantUser.Role.TENANT_ADMIN,
        TenantUser.Role.OWNER_ADMIN,
    }

    def list(self, request):
        tenant = getattr(request, 'tenant', None)
        qs = Invoice.objects.filter(tenant=tenant) if tenant else Invoice.objects.none()
        qs = qs.exclude(status='DRAFT')

        start = request.query_params.get('from')
        end = request.query_params.get('to')
        if start:
            qs = qs.filter(issue_date__gte=start)
        if end:
            qs = qs.filter(issue_date__lte=end)

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=[
            'Umsatz', 'Soll/Haben', 'Konto', 'Gegenkonto',
            'BU-Schlüssel', 'Belegdatum', 'Belegfeld 1', 'Buchungstext',
        ], delimiter=';', quoting=csv.QUOTE_ALL)
        writer.writeheader()

        for inv in qs.order_by('issue_date'):
            is_credit = inv.invoice_type == 'credit_note'
            contact_name = inv.contact.name if inv.contact else 'Unbekannt'

            writer.writerow({
                'Umsatz': str(abs(float(inv.total))).replace('.', ','),
                'Soll/Haben': 'H' if not is_credit else 'S',
                'Konto': '8400' if not is_credit else '8730',  # Erlöse / Erlösminderung
                'Gegenkonto': '10000',  # Forderungen
                'BU-Schlüssel': '3' if float(inv.tax_total) > 0 else '0',  # 3 = 19% MwSt
                'Belegdatum': inv.issue_date.strftime('%d%m') if inv.issue_date else '',
                'Belegfeld 1': inv.invoice_number or '',
                'Buchungstext': f'{"Gutschrift" if is_credit else "Rechnung"} {contact_name}',
            })

        resp = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="datev_export.csv"'
        return resp


router = DefaultRouter()
router.trailing_slash = '/?'
router.register('invoices', InvoiceViewSet, basename='billing-invoices')
router.register('reports/invoices/export', InvoiceExportView, basename='billing-invoices-export')
router.register('reports/datev', DATEVExportView, basename='billing-datev-export')
router.register('settings', BillingSettingsViewSet, basename='billing-settings')

api_urls = [path('billing/', include(router.urls))]
