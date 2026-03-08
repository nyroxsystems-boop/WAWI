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
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.views import APIView

from billing.models import Invoice, InvoiceLine
from billing.serializers import InvoiceSerializer
from outbox.utils import create_event
from channels.models import Contact
from tenancy.permissions import IsTenantOrServiceToken
from .adapters import fetch_offers_for_connection
from .models import (
    DealerSupplierSetting, MerchantSettings, Offer, Order, Product,
    PurchaseOrder, PurchaseOrderItem, StockItem, StockLocation,
    StockMovement, Supplier, SupplierArticle, WwsConnection,
)
from .serializers import (
    DealerSupplierSettingSerializer,
    OfferCreateSerializer,
    OfferSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    ProductSerializer,
    ProductListSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderCreateSerializer,
    PurchaseOrderItemSerializer,
    StockLocationSerializer,
    StockMovementSerializer,
    SupplierArticleSerializer,
    SupplierSerializer,
    WwsConnectionSerializer,
)

logger = logging.getLogger('inventree')


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

        # ── Inventory stats (new!) ──
        product_qs = Product.objects.filter(tenant=tenant)
        product_counts = product_qs.annotate(
            stock=Coalesce(models.Sum('stock_items__quantity'), 0),
        ).aggregate(
            total=models.Count('id'),
            low_stock=models.Count('id', filter=models.Q(stock__lt=models.F('minimum_stock'))),
            total_value=models.Sum(models.F('stock') * models.F('purchase_price')),
        )

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
                'totalProducts': product_counts['total'],
                'lowStockCount': product_counts['low_stock'],
                'totalValue': float(product_counts['total_value'] or 0),
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
# Routers and URL patterns
# ──────────────────────────────────────────────────────────────

router = DefaultRouter()
router.trailing_slash = '/?'
# Existing
router.register('orders', OrderViewSet, basename='wws-orders')
router.register('offers', OfferViewSet, basename='wws-offers')
router.register('suppliers', SupplierViewSet, basename='wws-suppliers')
router.register('wws-connections', WwsConnectionViewSet, basename='wws-connections')
# New inventory endpoints
router.register('products', ProductViewSet, basename='wws-products')
router.register('stock-locations', StockLocationViewSet, basename='wws-stock-locations')
router.register('stock-movements', StockMovementViewSet, basename='wws-stock-movements')
router.register('supplier-articles', SupplierArticleViewSet, basename='wws-supplier-articles')
router.register('purchase-orders', PurchaseOrderViewSet, basename='wws-purchase-orders')

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
