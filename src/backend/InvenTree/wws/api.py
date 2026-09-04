"""API definitions for WWS."""

import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import models, transaction
from django.db.models.functions import Coalesce
from django.urls import include, path
from django.utils import timezone
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.views import APIView

from billing.models import Invoice, InvoiceLine
from billing.serializers import InvoiceSerializer
from outbox.utils import create_event
from channels.models import Contact
from tenancy.models import TenantUser
from tenancy.permissions import IsTenantOrServiceToken
from tenancy.throttling import OemLookupThrottle
from .adapters import fetch_offers_for_connection
from .models import (
    BomItem, DealerSupplierSetting, MerchantSettings, OemCrossReference, Offer,
    Order, PriceRule, Product, PurchaseOrder, PurchaseOrderItem, Return,
    StockItem, StockLocation, StockMovement, Supplier, SupplierArticle,
    SupplierRating, VehicleApplication, WwsConnection,
)
from .serializers import (
    BomItemSerializer,
    DealerSupplierSettingSerializer,
    OemCrossReferenceSerializer,
    OfferCreateSerializer,
    OfferSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    PriceRuleSerializer,
    ProductSerializer,
    ProductListSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderCreateSerializer,
    PurchaseOrderItemSerializer,
    ReturnSerializer,
    StockLocationSerializer,
    StockMovementSerializer,
    SupplierArticleSerializer,
    SupplierRatingSerializer,
    SupplierSerializer,
    VehicleApplicationSerializer,
    WwsConnectionSerializer,
)

logger = logging.getLogger('inventree')


class WaWiPagination(PageNumberPagination):
    """Default pagination for all WaWi list endpoints."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class TenantScopedViewSet(viewsets.ModelViewSet):
    """Base viewset to scope by request.tenant."""

    permission_classes = [IsTenantOrServiceToken]
    pagination_class = WaWiPagination
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
    """Manage suppliers (full CRUD)."""

    serializer_class = SupplierSerializer
    queryset = Supplier.objects.all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'contact_person', 'email']
    ordering = ['name']


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
    tenant_read_roles = {
        TenantUser.Role.TENANT_ADMIN,
        TenantUser.Role.OWNER_ADMIN,
    }

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
    """Bot-facing endpoint to fetch offers by OEM. Searches internal catalog + external connections."""

    permission_classes = [IsTenantOrServiceToken]
    required_service_scope = 'bot.inventory.read'
    throttle_classes = [OemLookupThrottle]

    def get(self, request, oem):
        """Return normalized offers from internal products + external connections."""
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        cache_key = f'bot_inv:{tenant.id}:{oem}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        offers = []
        errors = []

        # ── Search internal Product catalog ──
        internal_products = Product.objects.filter(
            tenant=tenant, IPN__iexact=oem, status='active'
        ).prefetch_related('stock_items', 'supplier_articles__supplier')

        for product in internal_products:
            stock = product.total_in_stock
            # Add internal product as an offer
            offers.append({
                'source': 'internal',
                'product_id': product.id,
                'product_name': product.name,
                'brand': product.brand,
                'sku': product.IPN,
                'price': float(product.sale_price),
                'purchase_price': float(product.purchase_price),
                'currency': 'EUR',
                'availability': 'in_stock' if stock > 0 else 'out_of_stock',
                'stock_quantity': stock,
                'delivery_days': 0 if stock > 0 else None,
            })

            # Add supplier offers for this product
            for sa in product.supplier_articles.select_related('supplier').all():
                offers.append({
                    'source': 'supplier',
                    'supplier_id': sa.supplier_id,
                    'supplier_name': sa.supplier.name,
                    'product_name': product.name,
                    'brand': product.brand,
                    'sku': sa.supplier_sku or product.IPN,
                    'price': float(sa.purchase_price),
                    'currency': sa.currency,
                    'availability': 'available',
                    'delivery_days': sa.lead_time_days,
                    'minimum_order_quantity': sa.minimum_order_quantity,
                })

        # ── Search external WWS connections ──
        connections = WwsConnection.objects.filter(tenant=tenant, is_active=True)
        for connection in connections:
            try:
                result = fetch_offers_for_connection(connection, oem)
                offers.extend(result.get('offers') or [])
                if result.get('error'):
                    errors.append({
                        'connection_id': connection.id,
                        'error': result['error'],
                    })
            except Exception as exc:
                logger.warning('wws.connection.error', extra={
                    'connection_id': connection.id,
                    'oem': oem,
                    'error': str(exc),
                })
                errors.append({
                    'connection_id': connection.id,
                    'error': str(exc),
                })

        payload = {
            'oem': oem,
            'oemNumber': oem,
            'offers': offers,
            'totalOffers': len(offers),
            'internalProducts': internal_products.count(),
            'generated_at': timezone.now().isoformat(),
            'errors': errors,
        }
        cache.set(cache_key, payload, timeout=60)
        return Response(payload)


class BotHealth(APIView):
    """Simple health endpoint for bot."""

    permission_classes = [IsTenantOrServiceToken]
    required_service_scope = 'bot.health.read'

    def get(self, request):
        """Return ok — do not leak tenant details."""
        return Response({'status': 'ok'})


class BotConfig(APIView):
    """Expose config info for bot clients."""

    permission_classes = [IsTenantOrServiceToken]
    required_service_scope = 'bot.settings.read'

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
    """Aggregate stats for HeuteView — optimized with batch queries."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        today = timezone.now().date()
        fourteen_days_ago = today - timezone.timedelta(days=13)

        # ── Batch counts (1 query with conditional aggregation) ──
        order_counts = Order.objects.filter(tenant=tenant).aggregate(
            new=models.Count('id', filter=models.Q(status='new')),
            in_progress=models.Count('id', filter=models.Q(status__in=['processing', 'collect_part'])),
            total=models.Count('id'),
        )
        invoice_counts = Invoice.objects.filter(tenant=tenant).aggregate(
            draft=models.Count('id', filter=models.Q(status='DRAFT')),
            issued=models.Count('id', filter=models.Q(status='ISSUED')),
            paid_total=models.Sum('total', filter=models.Q(status='PAID')),
        )

        # ── Margin stats ──
        avg_margin = Offer.objects.filter(
            order__tenant=tenant, status='published'
        ).aggregate(avg=models.Avg('meta_json__margin_percent'))['avg'] or 0.0

        paid_total = invoice_counts['paid_total'] or Decimal('0.00')
        margin_revenue = float(paid_total) * (float(avg_margin) / 100.0)

        # ── Revenue today ──
        revenue_today = Invoice.objects.filter(
            tenant=tenant,
            status__in=['ISSUED', 'SENT', 'PAID'],
            issue_date=today,
        ).aggregate(total=models.Sum('total'))['total'] or Decimal('0.00')

        # ── Revenue history — 1 query instead of 14 ──
        from django.db.models.functions import TruncDate
        rev_by_day = dict(
            Invoice.objects.filter(
                tenant=tenant,
                status__in=['ISSUED', 'SENT', 'PAID'],
                issue_date__gte=fourteen_days_ago,
            ).values('issue_date').annotate(
                rev=models.Sum('total'),
            ).values_list('issue_date', 'rev')
        )
        orders_by_day = dict(
            Order.objects.filter(
                tenant=tenant,
                created_at__date__gte=fourteen_days_ago,
            ).annotate(
                day=TruncDate('created_at'),
            ).values('day').annotate(
                cnt=models.Count('id'),
            ).values_list('day', 'cnt')
        )
        last_14_days = []
        for i in range(13, -1, -1):
            day = today - timezone.timedelta(days=i)
            last_14_days.append({
                'date': day.strftime('%d.%m'),
                'revenue': float(rev_by_day.get(day, 0) or 0),
                'orders': orders_by_day.get(day, 0),
            })

        # ── Top customers ──
        top_customers_qs = Contact.objects.filter(tenant=tenant).annotate(
            revenue=models.Sum(
                'invoices__total',
                filter=models.Q(invoices__status__in=['ISSUED', 'SENT', 'PAID']),
            ),
            order_count=models.Count('orders', distinct=True),
        ).exclude(revenue__isnull=True).order_by('-revenue')[:5]

        top_customers = [{
            'name': c.name or c.wa_id,
            'revenue': float(c.revenue or 0),
            'orders': c.order_count,
            'avatar': (c.name or '??')[:2].upper(),
        } for c in top_customers_qs]

        # ── Recent activities ──
        recent_orders = Order.objects.filter(
            tenant=tenant,
        ).select_related('contact').order_by('-updated_at')[:10]
        activities = [{
            'id': f'order-{o.id}',
            'type': 'order' if o.status != 'new' else 'message',
            'customer': o.contact.name if o.contact else 'Unbekannt',
            'description': f'Status: {o.status} | OEM: {o.oem or "N/A"}',
            'time': o.updated_at.isoformat(),
            'status': 'processing' if o.status in ['new', 'processing'] else 'success',
        } for o in recent_orders]

        # ── Inventory stats ──
        product_qs = Product.objects.filter(tenant=tenant).annotate(
            stock=Coalesce(models.Sum('stock_items__quantity'), 0),
        )
        total_products = product_qs.count()
        low_stock_count = product_qs.filter(stock__lt=models.F('minimum_stock')).count()
        total_value = product_qs.aggregate(
            val=models.Sum(models.F('stock') * models.F('purchase_price'))
        )['val'] or Decimal('0.00')

        return Response({
            'ordersNew': order_counts['new'],
            'ordersInProgress': order_counts['in_progress'],
            'invoicesDraft': invoice_counts['draft'],
            'invoicesIssued': invoice_counts['issued'],
            'revenueToday': float(revenue_today),
            'revenueHistory': last_14_days,
            'topCustomers': top_customers,
            'activities': activities,
            'avgMargin': float(avg_margin),
            'marginRevenue': margin_revenue,
            'lastSync': timezone.now().isoformat(),
            # New inventory section
            'inventory': {
                'totalProducts': total_products,
                'lowStockCount': low_stock_count,
                'totalValue': float(total_value),
            },
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


# ──────────────────────────────────────────────────────────────
# Inventory ViewSets
# ──────────────────────────────────────────────────────────────


class ProductViewSet(TenantScopedViewSet):
    """Full CRUD for products / auto parts."""

    serializer_class = ProductSerializer
    queryset = Product.objects.all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'IPN', 'brand', 'description']
    ordering_fields = ['name', 'IPN', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Annotate total_in_stock for list performance
        qs = qs.annotate(
            total_in_stock=Coalesce(
                models.Sum('stock_items__quantity'), 0
            )
        )
        # Filters
        brand = self.request.query_params.get('brand')
        if brand:
            qs = qs.filter(brand__iexact=brand)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category_name__iexact=category)
        return qs

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Server-side aggregated stats."""
        tenant = getattr(request, 'tenant', None)
        qs = Product.objects.filter(tenant=tenant)
        total = qs.count()
        qs_annotated = qs.annotate(
            stock=Coalesce(models.Sum('stock_items__quantity'), 0)
        )
        low_stock = qs_annotated.filter(stock__lt=models.F('minimum_stock')).count()
        total_value = qs_annotated.aggregate(
            val=models.Sum(models.F('stock') * models.F('purchase_price'))
        )['val'] or Decimal('0.00')
        return Response({
            'totalArticles': total,
            'lowStockCount': low_stock,
            'totalValue': float(total_value),
        })

    @action(detail=False, methods=['get'], url_path='reorder-suggestions')
    def reorder_suggestions(self, request):
        """Server-side reorder suggestions."""
        tenant = getattr(request, 'tenant', None)
        qs = Product.objects.filter(tenant=tenant).annotate(
            stock=Coalesce(models.Sum('stock_items__quantity'), 0)
        ).filter(stock__lt=models.F('minimum_stock'))
        results = []
        for p in qs:
            results.append({
                'part': ProductListSerializer(p).data,
                'current_stock': p.stock,
                'minimum_stock': p.minimum_stock,
                'suggested_order_quantity': max(p.minimum_stock - p.stock, p.minimum_stock),
            })
        return Response(results)

    @action(detail=True, methods=['get'])
    def movements(self, request, pk=None):
        """Movement history for a specific product."""
        product = self.get_object()
        movements = StockMovement.objects.filter(
            tenant=request.tenant, product=product
        ).select_related('from_location', 'to_location', 'product')[:50]
        return Response(StockMovementSerializer(movements, many=True).data)

    @action(detail=True, methods=['get'])
    def suppliers(self, request, pk=None):
        """Supplier articles for a specific product."""
        product = self.get_object()
        articles = SupplierArticle.objects.filter(
            tenant=request.tenant, product=product
        ).select_related('supplier')
        return Response(SupplierArticleSerializer(articles, many=True).data)


class StockLocationViewSet(TenantScopedViewSet):
    """CRUD for warehouse locations."""

    serializer_class = StockLocationSerializer
    queryset = StockLocation.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.annotate(
            current_stock=Coalesce(
                models.Sum('stock_items__quantity'), 0
            )
        )
        return qs


class StockMovementViewSet(TenantScopedViewSet):
    """Create and list stock movements. Creating a movement auto-updates stock."""

    serializer_class = StockMovementSerializer
    queryset = StockMovement.objects.select_related('product', 'from_location', 'to_location')
    http_method_names = ['get', 'post', 'head', 'options']
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        part_id = self.request.query_params.get('part_id')
        if part_id:
            qs = qs.filter(product_id=part_id)
        limit = self.request.query_params.get('limit')
        if limit:
            try:
                qs = qs[:int(limit)]
            except (ValueError, TypeError):
                pass
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        """Create movement and update stock quantities."""
        tenant = getattr(self.request, 'tenant', None)
        user = self.request.user

        # Validate cross-tenant FK references
        product_id = serializer.validated_data.get('product', {})
        if hasattr(product_id, 'id'):
            product_id = product_id.id
        elif hasattr(product_id, 'pk'):
            product_id = product_id.pk
        else:
            product_id = serializer.validated_data.get('product_id') or serializer.initial_data.get('part_id')

        if product_id and tenant:
            if not Product.objects.filter(tenant=tenant, id=product_id).exists():
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'product': 'Product does not belong to your tenant.'})

        for loc_field in ['from_location', 'to_location']:
            loc = serializer.validated_data.get(loc_field)
            if loc and tenant:
                loc_id = loc.id if hasattr(loc, 'id') else loc
                if not StockLocation.objects.filter(tenant=tenant, id=loc_id).exists():
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError({loc_field: 'Location does not belong to your tenant.'})

        movement = serializer.save(
            tenant=tenant,
            created_by=getattr(user, 'username', 'system'),
        )
        product = movement.product
        mv_type = movement.type

        if mv_type == StockMovement.MovementType.IN and movement.to_location:
            item, _ = StockItem.objects.get_or_create(
                tenant=tenant, product=product, location=movement.to_location,
                defaults={'quantity': 0},
            )
            item.quantity += movement.quantity
            item.save(update_fields=['quantity', 'updated_at'])

        elif mv_type == StockMovement.MovementType.OUT and movement.from_location:
            item, _ = StockItem.objects.get_or_create(
                tenant=tenant, product=product, location=movement.from_location,
                defaults={'quantity': 0},
            )
            item.quantity = max(0, item.quantity - movement.quantity)
            item.save(update_fields=['quantity', 'updated_at'])

        elif mv_type == StockMovement.MovementType.TRANSFER:
            if movement.from_location:
                src, _ = StockItem.objects.get_or_create(
                    tenant=tenant, product=product, location=movement.from_location,
                    defaults={'quantity': 0},
                )
                src.quantity = max(0, src.quantity - movement.quantity)
                src.save(update_fields=['quantity', 'updated_at'])
            if movement.to_location:
                dst, _ = StockItem.objects.get_or_create(
                    tenant=tenant, product=product, location=movement.to_location,
                    defaults={'quantity': 0},
                )
                dst.quantity += movement.quantity
                dst.save(update_fields=['quantity', 'updated_at'])

        elif mv_type == StockMovement.MovementType.CORRECTION:
            loc = movement.to_location or movement.from_location
            if loc:
                item, _ = StockItem.objects.get_or_create(
                    tenant=tenant, product=product, location=loc,
                    defaults={'quantity': 0},
                )
                item.quantity = movement.quantity  # absolute set
                item.save(update_fields=['quantity', 'updated_at'])

        logger.info('stock.movement.created', extra={
            'tenant': getattr(tenant, 'slug', None),
            'product': product.IPN,
            'type': mv_type,
            'quantity': movement.quantity,
        })


class SupplierArticleViewSet(TenantScopedViewSet):
    """CRUD for supplier-product links."""

    serializer_class = SupplierArticleSerializer
    queryset = SupplierArticle.objects.select_related('supplier', 'product')

    def get_queryset(self):
        qs = super().get_queryset()
        supplier_id = self.request.query_params.get('supplier_id')
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        product_id = self.request.query_params.get('product_id')
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs


class PurchaseOrderViewSet(TenantScopedViewSet):
    """CRUD for purchase orders + receive action."""

    serializer_class = PurchaseOrderSerializer
    queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items__product')
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create PO with nested items."""
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        items_data = request.data.get('items', [])
        supplier_id = request.data.get('supplier')
        supplier = Supplier.objects.filter(tenant=tenant, id=supplier_id).first()
        if not supplier:
            return Response({'detail': 'Supplier not found'}, status=status.HTTP_400_BAD_REQUEST)

        po = PurchaseOrder.objects.create(
            tenant=tenant,
            supplier=supplier,
            expected_delivery=request.data.get('expected_delivery'),
            notes=request.data.get('notes', ''),
            currency=request.data.get('currency', 'EUR'),
        )
        # Auto-generate order number
        po.order_number = f'PO-{po.id:06d}'
        po.save(update_fields=['order_number'])

        for item_data in items_data:
            product = Product.objects.filter(
                tenant=tenant, id=item_data.get('product') or item_data.get('part_id')
            ).first()
            if product:
                PurchaseOrderItem.objects.create(
                    tenant=tenant,
                    purchase_order=po,
                    product=product,
                    quantity=item_data.get('quantity', 1),
                    unit_price=Decimal(str(item_data.get('unit_price', product.purchase_price))),
                )

        po.recalculate_total()
        return Response(
            PurchaseOrderSerializer(po).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """Receive goods for a PO — creates stock movements and updates stock."""
        po = self.get_object()
        tenant = getattr(request, 'tenant', None)

        if po.status in ('received', 'cancelled'):
            return Response(
                {'detail': f'Cannot receive PO in status {po.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        location_id = request.data.get('location_id')
        location = None
        if location_id:
            location = StockLocation.objects.filter(tenant=tenant, id=location_id).first()

        received_items = request.data.get('items', [])
        movements_created = []

        with transaction.atomic():
            for recv in received_items:
                poi = po.items.filter(
                    id=recv.get('item_id') or recv.get('id')
                ).first()
                if not poi:
                    continue

                qty = int(recv.get('quantity', poi.quantity))
                poi.received_quantity += qty
                poi.save(update_fields=['received_quantity', 'updated_at'])

                target_loc = location
                if not target_loc:
                    # Default to first location
                    target_loc = StockLocation.objects.filter(tenant=tenant).first()

                if target_loc:
                    movement = StockMovement.objects.create(
                        tenant=tenant,
                        product=poi.product,
                        type=StockMovement.MovementType.IN,
                        quantity=qty,
                        to_location=target_loc,
                        reference=f'PO-{po.order_number}',
                        notes=f'Received from {po.supplier.name}',
                        created_by=getattr(request.user, 'username', 'system'),
                    )
                    # Update stock
                    item, _ = StockItem.objects.get_or_create(
                        tenant=tenant, product=poi.product, location=target_loc,
                        defaults={'quantity': 0},
                    )
                    item.quantity += qty
                    item.save(update_fields=['quantity', 'updated_at'])
                    movements_created.append(movement.id)

            # Check if all items fully received
            all_received = all(
                poi.received_quantity >= poi.quantity for poi in po.items.all()
            )
            if all_received:
                po.status = PurchaseOrder.Status.RECEIVED
            else:
                po.status = PurchaseOrder.Status.CONFIRMED
            po.save(update_fields=['status', 'updated_at'])

        return Response({
            'status': po.status,
            'movements_created': len(movements_created),
            'order': PurchaseOrderSerializer(po).data,
        })


# ──────────────────────────────────────────────────────────────
# Feature 1: OEM Cross-Reference ViewSet
# ──────────────────────────────────────────────────────────────

class OemCrossReferenceViewSet(viewsets.ModelViewSet):
    """CRUD for OEM cross-references. Search by OEM number across all products."""

    permission_classes = [IsTenantOrServiceToken]
    serializer_class = OemCrossReferenceSerializer
    queryset = OemCrossReference.objects.select_related('product')
    pagination_class = WaWiPagination

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return self.queryset.none()
        qs = self.queryset.filter(tenant=tenant)
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        brand = self.request.query_params.get('brand')
        if brand:
            qs = qs.filter(brand__icontains=brand)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

    def perform_create(self, serializer):
        serializer.save(tenant=getattr(self.request, 'tenant', None))

    @action(detail=False, methods=['get'], url_path='search')
    def search_by_oem(self, request):
        """Search products by OEM number — resolves cross-references.

        GET /api/oem-cross-refs/search/?q=DF6134
        Returns the product(s) that match this OEM, plus the cross-ref details.
        """
        q = request.query_params.get('q', '').strip()
        if not q:
            return Response([])
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response([])

        # Search in cross-references
        xrefs = OemCrossReference.objects.filter(
            tenant=tenant, oem_number__icontains=q
        ).select_related('product')[:20]

        # Also search in Product.IPN directly
        direct = Product.objects.filter(
            tenant=tenant, IPN__icontains=q
        )[:20]

        results = []
        seen_product_ids = set()

        for xref in xrefs:
            if xref.product_id not in seen_product_ids:
                seen_product_ids.add(xref.product_id)
                results.append({
                    'product': ProductListSerializer(xref.product).data,
                    'matched_via': 'cross_reference',
                    'matched_oem': xref.oem_number,
                    'matched_brand': xref.brand,
                })

        for p in direct:
            if p.id not in seen_product_ids:
                seen_product_ids.add(p.id)
                results.append({
                    'product': ProductListSerializer(p).data,
                    'matched_via': 'direct_ipn',
                    'matched_oem': p.IPN,
                    'matched_brand': p.brand,
                })

        return Response(results)


# ──────────────────────────────────────────────────────────────
# Feature 3: Vehicle Application ViewSet
# ──────────────────────────────────────────────────────────────

class VehicleApplicationViewSet(viewsets.ModelViewSet):
    """CRUD for vehicle-to-product fitment data."""

    permission_classes = [IsTenantOrServiceToken]
    serializer_class = VehicleApplicationSerializer
    queryset = VehicleApplication.objects.select_related('product')
    pagination_class = WaWiPagination

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return self.queryset.none()
        qs = self.queryset.filter(tenant=tenant)
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        make = self.request.query_params.get('make')
        if make:
            qs = qs.filter(make__icontains=make)
        model_param = self.request.query_params.get('model')
        if model_param:
            qs = qs.filter(model__icontains=model_param)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

    def perform_create(self, serializer):
        serializer.save(tenant=getattr(self.request, 'tenant', None))

    @action(detail=False, methods=['get'], url_path='search')
    def search_by_vehicle(self, request):
        """Find parts for a vehicle.

        GET /api/vehicle-applications/search/?hsn=0603&tsn=BKP
        GET /api/vehicle-applications/search/?make=VW&model=Golf
        """
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response([])

        qs = VehicleApplication.objects.filter(tenant=tenant).select_related('product')

        hsn = request.query_params.get('hsn', '').strip()
        tsn = request.query_params.get('tsn', '').strip()
        make = request.query_params.get('make', '').strip()
        model_param = request.query_params.get('model', '').strip()

        if hsn:
            qs = qs.filter(kba_hsn__icontains=hsn)
        if tsn:
            qs = qs.filter(kba_tsn__icontains=tsn)
        if make:
            qs = qs.filter(make__icontains=make)
        if model_param:
            qs = qs.filter(model__icontains=model_param)

        results = []
        for va in qs[:50]:
            results.append({
                'product': ProductListSerializer(va.product).data,
                'vehicle': VehicleApplicationSerializer(va).data,
            })
        return Response(results)


# ──────────────────────────────────────────────────────────────
# Feature 2: Returns Management ViewSet
# ──────────────────────────────────────────────────────────────

class ReturnViewSet(viewsets.ModelViewSet):
    """CRUD for returns with workflow actions."""

    permission_classes = [IsTenantOrServiceToken]
    serializer_class = ReturnSerializer
    queryset = Return.objects.select_related('product', 'contact', 'order', 'location')
    pagination_class = WaWiPagination

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return self.queryset.none()
        qs = self.queryset.filter(tenant=tenant)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            tenant=getattr(self.request, 'tenant', None),
            created_by=user.username if user.is_authenticated else 'system',
        )

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a return request."""
        ret = self.get_object()
        if ret.status != 'requested':
            return Response({'detail': 'Can only approve requested returns.'}, status=status.HTTP_400_BAD_REQUEST)
        ret.status = 'approved'
        ret.save(update_fields=['status', 'updated_at'])
        return Response(ReturnSerializer(ret).data)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """Mark return as received and optionally restock."""
        ret = self.get_object()
        if ret.status not in ('approved', 'requested'):
            return Response({'detail': 'Return must be approved first.'}, status=status.HTTP_400_BAD_REQUEST)
        ret.status = 'received'
        ret.save(update_fields=['status', 'updated_at'])

        # Optionally restock if product and location provided
        restock = request.data.get('restock', False)
        if restock and ret.product and ret.location:
            tenant = getattr(request, 'tenant', None)
            stock_item, _ = StockItem.objects.get_or_create(
                tenant=tenant, product=ret.product, location=ret.location,
                defaults={'quantity': 0}
            )
            stock_item.quantity += ret.quantity
            stock_item.save()
            StockMovement.objects.create(
                tenant=tenant,
                product=ret.product,
                type='IN',
                quantity=ret.quantity,
                to_location=ret.location,
                reference=f'Return #{ret.id}',
                notes=f'Restock from return: {ret.reason}',
                created_by=request.user.username if request.user.is_authenticated else 'system',
            )

        return Response(ReturnSerializer(ret).data)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """Mark return as refunded. Optionally create a credit note."""
        ret = self.get_object()
        if ret.status not in ('received', 'inspected'):
            return Response({'detail': 'Return must be received first.'}, status=status.HTTP_400_BAD_REQUEST)

        refund_amount = request.data.get('refund_amount')
        if refund_amount is not None:
            ret.refund_amount = refund_amount

        ret.status = 'refunded'
        ret.save(update_fields=['status', 'refund_amount', 'updated_at'])

        # Create credit note invoice if requested
        create_credit = request.data.get('create_credit_note', False)
        credit_note = None
        if create_credit and ret.refund_amount > 0:
            tenant = getattr(request, 'tenant', None)
            from decimal import Decimal
            credit_note = Invoice.objects.create(
                tenant=tenant,
                order=ret.order,
                contact=ret.contact,
                invoice_type='credit_note',
                status='ISSUED',
                currency='EUR',
            )
            InvoiceLine.objects.create(
                tenant=tenant,
                invoice=credit_note,
                description=f'Gutschrift: Return #{ret.id}',
                quantity=ret.quantity,
                unit_price=-abs(ret.refund_amount),
                tax_rate=0,
            )
            credit_note.recalculate_totals()
            credit_note.save()

        data = ReturnSerializer(ret).data
        if credit_note:
            data['credit_note_id'] = credit_note.id
        return Response(data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a return request."""
        ret = self.get_object()
        ret.status = 'rejected'
        ret.notes = request.data.get('reason', ret.notes)
        ret.save(update_fields=['status', 'notes', 'updated_at'])
        return Response(ReturnSerializer(ret).data)


# ──────────────────────────────────────────────────────────────
# Feature 5: Price Rules ViewSet
# ──────────────────────────────────────────────────────────────

class PriceRuleViewSet(viewsets.ModelViewSet):
    """CRUD for quantity/profile-based pricing rules."""

    permission_classes = [IsTenantOrServiceToken]
    serializer_class = PriceRuleSerializer
    queryset = PriceRule.objects.select_related('product')
    pagination_class = WaWiPagination

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return self.queryset.none()
        qs = self.queryset.filter(tenant=tenant)
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        profile = self.request.query_params.get('profile')
        if profile:
            qs = qs.filter(profile=profile)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

    def perform_create(self, serializer):
        serializer.save(tenant=getattr(self.request, 'tenant', None))

    @action(detail=False, methods=['get'], url_path='calculate')
    def calculate_price(self, request):
        """Calculate the best price for a product given quantity and profile.

        GET /api/price-rules/calculate/?product=5&quantity=10&profile=werkstatt
        """
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'detail': 'Tenant required'}, status=status.HTTP_403_FORBIDDEN)

        product_id = request.query_params.get('product')
        quantity = int(request.query_params.get('quantity', 1))
        profile = request.query_params.get('profile', 'endkunde')

        if not product_id:
            return Response({'detail': 'product parameter required'}, status=status.HTTP_400_BAD_REQUEST)

        product = Product.objects.filter(tenant=tenant, id=product_id).first()
        if not product:
            return Response({'detail': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        from django.utils import timezone
        today = timezone.now().date()

        # Find best matching price rule
        rule = PriceRule.objects.filter(
            tenant=tenant, product=product, profile=profile,
            min_quantity__lte=quantity,
        ).filter(
            models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=today),
        ).filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=today),
        ).order_by('-min_quantity').first()

        if rule:
            if rule.discount_percent > 0:
                final_price = float(product.sale_price) * (1 - float(rule.discount_percent) / 100)
            else:
                final_price = float(rule.price)
        else:
            final_price = float(product.sale_price)

        return Response({
            'product_id': product.id,
            'product_ipn': product.IPN,
            'profile': profile,
            'quantity': quantity,
            'base_price': float(product.sale_price),
            'final_price': round(final_price, 2),
            'rule_applied': PriceRuleSerializer(rule).data if rule else None,
        })


# ──────────────────────────────────────────────────────────────
# Feature 7: BOM Items ViewSet
# ──────────────────────────────────────────────────────────────

class BomItemViewSet(viewsets.ModelViewSet):
    """CRUD for Bill of Materials (kit/set components)."""

    permission_classes = [IsTenantOrServiceToken]
    serializer_class = BomItemSerializer
    queryset = BomItem.objects.select_related('parent', 'component')
    pagination_class = WaWiPagination

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return self.queryset.none()
        qs = self.queryset.filter(tenant=tenant)
        parent_id = self.request.query_params.get('parent')
        if parent_id:
            qs = qs.filter(parent_id=parent_id)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

    def perform_create(self, serializer):
        serializer.save(tenant=getattr(self.request, 'tenant', None))

    @action(detail=False, methods=['post'], url_path='explode')
    def explode_bom(self, request):
        """Sell a set/kit: deduct all BOM component stock from the given location.

        POST /api/bom-items/explode/  {"parent": 5, "location": 3, "quantity": 1}
        """
        tenant = getattr(request, 'tenant', None)
        parent_id = request.data.get('parent')
        location_id = request.data.get('location')
        qty = int(request.data.get('quantity', 1))

        if not all([tenant, parent_id, location_id]):
            return Response({'detail': 'parent, location required'}, status=status.HTTP_400_BAD_REQUEST)

        bom_items = BomItem.objects.filter(tenant=tenant, parent_id=parent_id).select_related('component')
        if not bom_items:
            return Response({'detail': 'No BOM items found'}, status=status.HTTP_404_NOT_FOUND)

        deducted = []
        for bi in bom_items:
            needed = bi.quantity * qty
            stock_item = StockItem.objects.filter(
                tenant=tenant, product=bi.component, location_id=location_id
            ).first()
            if stock_item:
                stock_item.quantity = max(0, stock_item.quantity - needed)
                stock_item.save()
                StockMovement.objects.create(
                    tenant=tenant, product=bi.component, type='OUT',
                    quantity=needed, from_location_id=location_id,
                    reference=f'BOM explode: {bi.parent.IPN}',
                    created_by=request.user.username if request.user.is_authenticated else 'system',
                )
            deducted.append({'component': bi.component.IPN, 'qty_deducted': needed})

        return Response({'deducted': deducted})


# ──────────────────────────────────────────────────────────────
# Feature 8: Supplier Rating ViewSet
# ──────────────────────────────────────────────────────────────

class SupplierRatingViewSet(viewsets.ModelViewSet):
    """CRUD for supplier performance ratings."""

    permission_classes = [IsTenantOrServiceToken]
    serializer_class = SupplierRatingSerializer
    queryset = SupplierRating.objects.select_related('supplier')
    pagination_class = WaWiPagination

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return self.queryset.none()
        qs = self.queryset.filter(tenant=tenant)
        supplier_id = self.request.query_params.get('supplier')
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['tenant'] = getattr(self.request, 'tenant', None)
        return ctx

    def perform_create(self, serializer):
        instance = serializer.save(tenant=getattr(self.request, 'tenant', None))
        instance.compute_overall()
        instance.save(update_fields=['overall_score'])

    def perform_update(self, serializer):
        instance = serializer.save()
        instance.compute_overall()
        instance.save(update_fields=['overall_score'])

    @action(detail=True, methods=['post'])
    def recalculate(self, request, pk=None):
        """Recalculate overall score for a supplier rating."""
        rating = self.get_object()
        rating.compute_overall()
        rating.save(update_fields=['overall_score'])
        return Response(SupplierRatingSerializer(rating).data)


# ──────────────────────────────────────────────────────────────
# Routers and URL patterns
# ──────────────────────────────────────────────────────────────

router = DefaultRouter()
router.trailing_slash = '/?'
# Existing
router.register('orders', OrderViewSet, basename='wws-orders')
router.register('offers', OfferViewSet, basename='wws-offers')
router.register('suppliers', SupplierViewSet, basename='wws-suppliers')
router.register('wws-connections', WwsConnectionViewSet, basename='wws-connections')
# Inventory
router.register('products', ProductViewSet, basename='wws-products')
router.register('stock-locations', StockLocationViewSet, basename='wws-stock-locations')
router.register('stock-movements', StockMovementViewSet, basename='wws-stock-movements')
router.register('supplier-articles', SupplierArticleViewSet, basename='wws-supplier-articles')
router.register('purchase-orders', PurchaseOrderViewSet, basename='wws-purchase-orders')
# New features
router.register('oem-cross-refs', OemCrossReferenceViewSet, basename='wws-oem-cross-refs')
router.register('vehicle-applications', VehicleApplicationViewSet, basename='wws-vehicle-applications')
router.register('returns', ReturnViewSet, basename='wws-returns')
router.register('price-rules', PriceRuleViewSet, basename='wws-price-rules')
router.register('bom-items', BomItemViewSet, basename='wws-bom-items')
router.register('supplier-ratings', SupplierRatingViewSet, basename='wws-supplier-ratings')

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
