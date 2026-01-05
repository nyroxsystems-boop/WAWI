"""API definitions for WWS."""

from decimal import Decimal
from django.core.cache import cache
from django.db import models, transaction
from django.urls import include, path
from django.utils import timezone
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.views import APIView

from billing.models import Invoice, InvoiceLine
from billing.serializers import InvoiceSerializer
from outbox.utils import create_event
from channels.models import Contact
from tenancy.permissions import IsTenantOrServiceToken
from .adapters import fetch_offers_for_connection
from .models import DealerSupplierSetting, Offer, Order, Supplier, WwsConnection, MerchantSettings
from .serializers import (
    DealerSupplierSettingSerializer,
    OfferCreateSerializer,
    OfferSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    SupplierSerializer,
    WwsConnectionSerializer,
)


class TenantScopedViewSet(viewsets.ModelViewSet):
    """Base viewset to scope by request.tenant."""

    permission_classes = [IsTenantOrServiceToken]
    pagination_class = None
    queryset = None

    def get_serializer_context(self):
        """Inject tenant into serializer context for tenant-aware serializers."""
        context = super().get_serializer_context()
        context['tenant'] = getattr(self.request, 'tenant', None)
        return context

    def get_queryset(self):
        """Limit queryset to tenant."""
        tenant = getattr(self.request, 'tenant', None)
        if tenant is None:
            return self.queryset.none()
        qs = self.queryset.filter(tenant=tenant)
        return qs

    def perform_create(self, serializer):
        """Assign tenant on create."""
        serializer.save(tenant=getattr(self.request, 'tenant', None))


class SupplierViewSet(TenantScopedViewSet):
    """Manage suppliers."""

    serializer_class = SupplierSerializer
    queryset = Supplier.objects.all()
    http_method_names = ['get', 'post', 'head', 'options']


class OrderViewSet(TenantScopedViewSet):
    """Orders list/detail/create."""

    serializer_class = OrderSerializer
    queryset = Order.objects.select_related('contact')
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ['created_at', 'updated_at']
    search_fields = ['external_ref', 'oem']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def create(self, request, *args, **kwargs):
        """Return full order payload on create."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        order = serializer.instance
        output = OrderSerializer(order, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_serializer_class(self):
        """Use create serializer for POST."""
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer

    def perform_create(self, serializer):
        """Assign tenant and enqueue outbox event."""
        super().perform_create(serializer)
        tenant = getattr(self.request, 'tenant', None)
        if tenant:
            create_event('ORDER_CREATED', tenant, {'order_id': serializer.instance.id})

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm(self, request, pk=None):
        """Confirm order (bot/dashboard)."""
        order = self.get_object()
        new_status = request.data.get('status') or 'confirmed'
        if new_status:
            order.status = new_status
        if 'total_price' in request.data:
            order.total_price = request.data.get('total_price') or order.total_price
        if 'currency' in request.data:
            order.currency = request.data.get('currency') or order.currency
        order.save()
        return Response(OrderSerializer(order).data)

    def get_queryset(self):
        """Tenant scope with filters."""
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        start = self.request.query_params.get('from')
        end = self.request.query_params.get('to')

        if status_param:
            qs = qs.filter(status=status_param)
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)

        return qs

    @action(detail=True, methods=['get', 'post'], url_path='offers')
    def offers(self, request, pk=None):
        """List or create offers for an order."""
        order = self.get_object()
        if request.method.lower() == 'get':
            offers = order.offers.all()
            data = OfferSerializer(offers, many=True).data
            return Response(data)

        serializer = OfferCreateSerializer(
            data=request.data, context={'tenant': request.tenant, 'order': order}
        )
        serializer.is_valid(raise_exception=True)
        offer = serializer.save()
        return Response(OfferSerializer(offer).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='offers/publish')
    def publish_offers(self, request, pk=None):
        """Publish offers for an order (dashboard)."""
        order = self.get_object()
        offer_ids = request.data.get('offerIds') or request.data.get('offer_ids') or []
        if not isinstance(offer_ids, list):
            return Response({'detail': 'offerIds must be a list'}, status=status.HTTP_400_BAD_REQUEST)

        updated = Offer.objects.filter(order=order, id__in=offer_ids).update(
            status=Offer.OfferStatus.PUBLISHED
        )
        return Response({'success': True, 'updated': updated})

    @action(detail=True, methods=['post'], url_path='create-invoice')
    def create_invoice(self, request, pk=None):
        """Create a draft invoice from an order and its offers."""
        order = self.get_object()
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        invoice = Invoice.objects.create(
            tenant=tenant,
            order=order,
            contact=order.contact,
            currency=order.currency or 'EUR',
            status=Invoice.Status.DRAFT,
        )

        offers = list(order.offers.all())
        if offers:
            for offer in offers:
                InvoiceLine.objects.create(
                    tenant=tenant,
                    invoice=invoice,
                    description=offer.product_name or offer.brand or 'Angebot',
                    quantity=1,
                    unit_price=offer.price,
                    tax_rate=offer.meta_json.get('tax_rate', 0) if offer.meta_json else 0,
                )
        else:
            unit_price = order.total_price if order.total_price is not None else Decimal('0')
            InvoiceLine.objects.create(
                tenant=tenant,
                invoice=invoice,
                description=order.oem or 'Bestellung',
                quantity=1,
                unit_price=unit_price,
                tax_rate=0,
            )

        invoice.recalculate_totals()
        invoice.save()

        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class OfferViewSet(TenantScopedViewSet):
    """Direct offer listing if needed."""

    serializer_class = OfferSerializer
    queryset = Offer.objects.select_related('supplier', 'order')
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        """Support order filter."""
        qs = super().get_queryset()
        order_id = self.request.query_params.get('order')
        if order_id:
            qs = qs.filter(order_id=order_id)
        return qs


class WwsConnectionViewSet(TenantScopedViewSet):
    """Manage connections."""

    serializer_class = WwsConnectionSerializer
    queryset = WwsConnection.objects.all()
    http_method_names = ['get', 'post', 'patch', 'put', 'delete', 'head', 'options']

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Return dummy test result."""
        connection = self.get_object()
        return Response({
            'ok': True,
            'connectionId': connection.id,
            'sampleResultsCount': 0,
            'testedAt': timezone.now().isoformat(),
        })


class DealerSuppliersView(APIView):
    """Expose dealer supplier settings for dashboard compatibility."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request, dealer_id):
        """Return supplier settings for the tenant."""
        tenant = getattr(request, 'tenant', None)
        if tenant is None or str(tenant.id) != str(dealer_id):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        settings_qs = (
            DealerSupplierSetting.objects.select_related('supplier')
            .filter(tenant=tenant)
            .order_by('priority')
        )

        # Seed defaults if none exist
        if not settings_qs.exists():
            for idx, supplier in enumerate(Supplier.objects.filter(tenant=tenant)[:5]):
                DealerSupplierSetting.objects.create(
                    tenant=tenant,
                    supplier=supplier,
                    enabled=True,
                    is_default=idx == 0,
                    priority=(idx + 1) * 10,
                )
            settings_qs = DealerSupplierSetting.objects.select_related('supplier').filter(
                tenant=tenant
            )

        serializer = DealerSupplierSettingSerializer(settings_qs, many=True)
        return Response(serializer.data)

    def put(self, request, dealer_id):
        """Update supplier settings."""
        tenant = getattr(request, 'tenant', None)
        if tenant is None or str(tenant.id) != str(dealer_id):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        serializer = DealerSupplierSettingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data.get('items', [])

        with transaction.atomic():
            for item in items:
                supplier_id = item.get('supplier_id') or item.get('supplier')
                if supplier_id is None:
                    continue
                setting, _ = DealerSupplierSetting.objects.get_or_create(
                    tenant=tenant, supplier_id=supplier_id, defaults={'priority': 10}
                )
                setting.enabled = bool(item.get('enabled', True))
                setting.priority = int(item.get('priority', setting.priority or 10))
                setting.is_default = bool(item.get('is_default', False))
                setting.save()

        settings_qs = DealerSupplierSetting.objects.select_related('supplier').filter(
            tenant=tenant
        )
        return Response(DealerSupplierSettingSerializer(settings_qs, many=True).data)


class BotInventoryByOem(APIView):
    """Bot-facing endpoint to fetch offers by OEM."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request, oem):
        """Return normalized offers."""
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        cache_key = f'bot_inv:{tenant.id}:{oem}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        offers = []
        errors = []

        connections = WwsConnection.objects.filter(tenant=tenant, is_active=True)
        for connection in connections:
            result = fetch_offers_for_connection(connection, oem)
            offers.extend(result.get('offers') or [])
            if result.get('error'):
                errors.append({
                    'connection_id': connection.id,
                    'error': result['error'],
                })

        payload = {
            'oem': oem,
            'oemNumber': oem,
            'offers': offers,
            'generated_at': timezone.now().isoformat(),
            'errors': errors,
        }
        cache.set(cache_key, payload, timeout=60)
        return Response(payload)


class BotHealth(APIView):
    """Simple health endpoint for bot."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        """Return ok."""
        tenant = getattr(request, 'tenant', None)
        return Response({'status': 'ok', 'tenant_id': tenant.id if tenant else None})


class BotConfig(APIView):
    """Expose config info for bot clients."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        """Return readonly config summary."""
        tenant = getattr(request, 'tenant', None)
        connections = WwsConnection.objects.filter(
            tenant=tenant, is_active=True
        ).values('id', 'type', 'base_url')
        return Response({
            'tenant_id': tenant.id if tenant else None,
            'connections': list(connections),
            'requires_service_token': True,
        })


DEFAULT_PRICE_PROFILES = [
    {
        'id': 'standard',
        'name': 'Standard (Endkunde)',
        'description': 'Standard-Verkaufspreis an Endkunden.',
        'margin': 0.40,
        'isDefault': True,
    },
    {
        'id': 'workshop_basic',
        'name': 'Werkstatt Basic',
        'description': 'Rabattierter Preis für Mechaniker und kleine Werkstätten.',
        'margin': 0.28,
    },
    {
        'id': 'workshop_pro',
        'name': 'Werkstatt Pro',
        'description': 'Partnerkondition für größere Werkstätten und Betriebe.',
        'margin': 0.22,
    },
    {
        'id': 'partner',
        'name': 'Händler / Partner',
        'description': 'Niedrigere Marge für Händlerkollegen und B2B-Partner.',
        'margin': 0.10,
    },
]


class MerchantSettingsView(APIView):
    """Dashboard merchant settings endpoints. Get/Set merchant settings."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request, merchant_id=None):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
             return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)
        
        settings_obj, _ = MerchantSettings.objects.get_or_create(
            tenant=tenant,
            defaults={
                'selected_shops': [],
                'margin_percent': Decimal('0.00'),
                'price_profiles': [],
            },
        )
        return Response({
            'merchantId': str(tenant.id),
            'selectedShops': settings_obj.selected_shops,
            'marginPercent': float(settings_obj.margin_percent),
            'priceProfiles': settings_obj.price_profiles,
        })

    def post(self, request, merchant_id=None):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)
            
        settings_obj, _ = MerchantSettings.objects.get_or_create(tenant=tenant)
        if 'selectedShops' in request.data:
            settings_obj.selected_shops = request.data.get('selectedShops') or []
        if 'marginPercent' in request.data:
            settings_obj.margin_percent = Decimal(str(request.data.get('marginPercent') or 0))
        if 'priceProfiles' in request.data:
            settings_obj.price_profiles = request.data.get('priceProfiles') or []
        settings_obj.save()
        return Response({'ok': True})


class DashboardSummaryView(APIView):
    """Aggregate stats for HeuteView."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        # Basic counts
        orders_new = Order.objects.filter(tenant=tenant, status='new').count()
        orders_in_progress = Order.objects.filter(tenant=tenant, status__in=['processing', 'collect_part']).count()
        
        invoices_issued = Invoice.objects.filter(tenant=tenant, status='ISSUED').count()
        invoices_draft = Invoice.objects.filter(tenant=tenant, status='DRAFT').count()
        
        # Margin stats
        margin_qs = Offer.objects.filter(
            order__tenant=tenant,
            status='published'
        ).aggregate(avg_margin=models.Avg('meta_json__margin_percent'))
        avg_margin = margin_qs['avg_margin'] or 0.0

        # Estimate margin revenue from paid invoices (simplified)
        paid_invoices_sum = Invoice.objects.filter(
            tenant=tenant, status='PAID'
        ).aggregate(models.Sum('total'))['total__sum'] or Decimal('0.00')
        margin_revenue = float(paid_invoices_sum) * (float(avg_margin) / 100.0)

        # Revenue history (last 14 days)
        today = timezone.now().date()
        revenue_today = Invoice.objects.filter(
            tenant=tenant, 
            status__in=['ISSUED', 'SENT', 'PAID'],
            issue_date=today
        ).aggregate(models.Sum('total'))['total__sum'] or Decimal('0.00')

        last_14_days = []
        for i in range(13, -1, -1):
            day = today - timezone.timedelta(days=i)
            rev = Invoice.objects.filter(
                tenant=tenant,
                status__in=['ISSUED', 'SENT', 'PAID'],
                issue_date=day
            ).aggregate(models.Sum('total'))['total__sum'] or Decimal('0.00')
            last_14_days.append({
                'date': day.strftime('%d.%m'),
                'revenue': float(rev),
                'orders': Order.objects.filter(tenant=tenant, created_at__date=day).count()
            })

        # Top customers (by invoice total)
        top_customers_qs = Contact.objects.filter(tenant=tenant).annotate(
            revenue=models.Sum('invoices__total', filter=models.Q(invoices__status__in=['ISSUED', 'SENT', 'PAID'])),
            order_count=models.Count('orders', distinct=True)
        ).order_by('-revenue')[:5]
        
        top_customers = []
        for c in top_customers_qs:
            top_customers.append({
                'name': c.name or c.wa_id,
                'revenue': float(c.revenue or 0),
                'orders': c.order_count,
                'avatar': (c.name or '??')[:2].upper()
            })

        # Recent activities
        recent_orders = Order.objects.filter(tenant=tenant).select_related('contact').order_by('-updated_at')[:10]
        activities = []
        for o in recent_orders:
            activities.append({
                'id': f'order-{o.id}',
                'type': 'order' if o.status != 'new' else 'message',
                'customer': o.contact.name if o.contact else 'Unbekannt',
                'description': f'Status: {o.status} | OEM: {o.oem or "N/A"}',
                'time': o.updated_at.isoformat(),
                'status': 'processing' if o.status in ['new', 'processing'] else 'success'
            })

        return Response({
            'ordersNew': orders_new,
            'ordersInProgress': orders_in_progress,
            'invoicesDraft': invoices_draft,
            'invoicesIssued': invoices_issued,
            'revenueToday': float(revenue_today),
            'revenueHistory': last_14_days,
            'topCustomers': top_customers,
            'activities': activities,
            'avgMargin': float(avg_margin),
            'marginRevenue': margin_revenue,
            'lastSync': timezone.now().isoformat(),
        })


class RequestIntakeView(APIView):
    """Minimal endpoint for bot request/order intake."""

    permission_classes = [IsTenantOrServiceToken]

    def post(self, request):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        contact = None
        contact_id = request.data.get('contact') or request.data.get('contact_id')
        if contact_id:
            contact = Contact.objects.filter(id=contact_id, tenant=tenant).first()
        elif request.data.get('wa_id'):
            wa_id = request.data.get('wa_id')
            contact, _ = Contact.objects.get_or_create(
                tenant=tenant, wa_id=wa_id, defaults={'name': request.data.get('name', '')}
            )

        order = Order.objects.create(
            tenant=tenant,
            status=request.data.get('status') or 'new',
            language=request.data.get('language') or '',
            order_data=request.data.get('order_data') or request.data.get('data') or {},
            vehicle_json=request.data.get('vehicle_json') or request.data.get('vehicle') or {},
            part_json=request.data.get('part_json') or request.data.get('part') or {},
            contact=contact,
            oem=request.data.get('oem') or '',
            notes=request.data.get('notes') or '',
            total_price=request.data.get('total_price') or 0,
            currency=request.data.get('currency') or 'EUR',
        )
        create_event('ORDER_CREATED', tenant, {'order_id': order.id})
        return Response({'order_id': order.id, 'order': OrderSerializer(order).data}, status=status.HTTP_201_CREATED)


# Routers and URL patterns
router = DefaultRouter()
router.trailing_slash = '/?'
router.register('orders', OrderViewSet, basename='wws-orders')
router.register('offers', OfferViewSet, basename='wws-offers')
router.register('suppliers', SupplierViewSet, basename='wws-suppliers')
router.register('wws-connections', WwsConnectionViewSet, basename='wws-connections')

api_urls = [
    path('', include(router.urls)),
    path('dealers/<int:dealer_id>/suppliers', DealerSuppliersView.as_view(), name='dealer-suppliers'),
    path('requests', RequestIntakeView.as_view(), name='request-intake'),
    path('bot/inventory/by-oem/<str:oem>', BotInventoryByOem.as_view(), name='bot-inventory-by-oem'),
    path('bot/health', BotHealth.as_view(), name='bot-health'),
    path('bot/config', BotConfig.as_view(), name='bot-config'),
]

# Dashboard compat: expose the same endpoints under /dashboard prefix
dashboard_urls = [
    path('dashboard/', include(router.urls)),
    path('dashboard/dealers/<int:dealer_id>/suppliers', DealerSuppliersView.as_view(), name='dashboard-dealer-suppliers'),
    path('dashboard/merchant/settings/', MerchantSettingsView.as_view(), name='dashboard-merchant-settings'),
    path('dashboard/merchant/settings/<int:merchant_id>', MerchantSettingsView.as_view(), name='dashboard-merchant-settings-id'),
    path('dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
]
