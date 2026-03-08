"""AI-powered endpoints for WaWi intelligence features.

Features 9-14: Smart Reorder, OEM Resolution, Price Optimization,
Image Article Creation, Anomaly Detection, Chat Summary.
"""

import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.permissions import IsTenantOrServiceToken
from .models import (
    OemCrossReference, Product, PurchaseOrder, Return, StockItem,
    StockMovement, Supplier, SupplierRating,
)
from .serializers import ProductListSerializer

logger = logging.getLogger('inventree')


# ──────────────────────────────────────────────────────────────
# Feature 9: Smart Reorder — Demand Forecasting
# ──────────────────────────────────────────────────────────────

class SmartReorderView(APIView):
    """Analyzes historical stock movements to predict demand and generate
    reorder suggestions with estimated quantities.

    GET /api/ai/smart-reorder/
    Query params:
        - days: lookback period (default 90)
        - forecast_days: forward prediction (default 30)
    """

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response([], status=status.HTTP_403_FORBIDDEN)

        lookback = int(request.query_params.get('days', 90))
        forecast_days = int(request.query_params.get('forecast_days', 30))
        cutoff = timezone.now() - timedelta(days=lookback)

        # Aggregate OUT movements per product in the lookback window
        demand = StockMovement.objects.filter(
            tenant=tenant, type='OUT', created_at__gte=cutoff,
        ).values('product_id').annotate(
            total_out=Sum('quantity'),
            movement_count=Count('id'),
        ).order_by('-total_out')

        suggestions = []
        for row in demand:
            product = Product.objects.filter(
                tenant=tenant, id=row['product_id'], status='active',
            ).first()
            if not product:
                continue

            total_out = row['total_out'] or 0
            daily_rate = total_out / max(lookback, 1)
            forecasted_demand = round(daily_rate * forecast_days)
            current_stock = product.total_in_stock

            # Check if reorder is needed
            days_of_stock = round(current_stock / daily_rate) if daily_rate > 0 else 999
            reorder_qty = max(0, forecasted_demand - current_stock + product.minimum_stock)

            if reorder_qty <= 0:
                continue

            # Find best supplier
            best_supplier = product.supplier_articles.filter(
                is_preferred=True
            ).select_related('supplier').first()
            if not best_supplier:
                best_supplier = product.supplier_articles.order_by(
                    'purchase_price'
                ).select_related('supplier').first()

            # Seasonality factor (compare this month vs average)
            from datetime import date
            current_month = timezone.now().month
            monthly_data = StockMovement.objects.filter(
                tenant=tenant, type='OUT', product=product,
                created_at__gte=timezone.now() - timedelta(days=365),
            ).extra(
                select={'month': "EXTRACT(month FROM created_at)"}
            ).values('month').annotate(total=Sum('quantity'))

            monthly_map = {int(d['month']): d['total'] for d in monthly_data}
            avg_monthly = sum(monthly_map.values()) / max(len(monthly_map), 1)
            current_monthly = monthly_map.get(current_month, 0)
            seasonality = round(current_monthly / avg_monthly, 2) if avg_monthly > 0 else 1.0

            suggestions.append({
                'product': ProductListSerializer(product).data,
                'daily_rate': round(daily_rate, 2),
                'forecasted_demand': forecasted_demand,
                'current_stock': current_stock,
                'days_of_stock_remaining': days_of_stock,
                'reorder_quantity': reorder_qty,
                'urgency': 'critical' if days_of_stock < 7 else 'warning' if days_of_stock < 14 else 'normal',
                'seasonality_factor': seasonality,
                'suggested_supplier': {
                    'id': best_supplier.supplier.id,
                    'name': best_supplier.supplier.name,
                    'price': float(best_supplier.purchase_price),
                    'lead_time_days': best_supplier.lead_time_days,
                } if best_supplier else None,
                'estimated_cost': float(best_supplier.purchase_price * reorder_qty) if best_supplier else None,
            })

        # Sort by urgency
        urgency_order = {'critical': 0, 'warning': 1, 'normal': 2}
        suggestions.sort(key=lambda s: (urgency_order.get(s['urgency'], 3), -s['reorder_quantity']))

        return Response({
            'lookback_days': lookback,
            'forecast_days': forecast_days,
            'suggestions': suggestions,
            'total_estimated_cost': sum(s['estimated_cost'] or 0 for s in suggestions),
        })


# ──────────────────────────────────────────────────────────────
# Feature 10: Intelligent OEM Resolution (Fuzzy Search)
# ──────────────────────────────────────────────────────────────

class FuzzyOemSearchView(APIView):
    """Fuzzy OEM number search — normalizes input and finds matches
    across products and cross-references.

    GET /api/ai/oem-search/?q=1K0-615 301AD
    """

    permission_classes = [IsTenantOrServiceToken]

    @staticmethod
    def normalize_oem(oem: str) -> str:
        """Remove spaces, dashes, dots for fuzzy matching."""
        return ''.join(c for c in oem.upper() if c.isalnum())

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response([])

        query = request.query_params.get('q', '').strip()
        if not query or len(query) < 3:
            return Response([])

        normalized = self.normalize_oem(query)

        # Search in Product.IPN
        products = Product.objects.filter(tenant=tenant, status='active')
        results = []
        seen = set()

        for p in products.iterator():
            if self.normalize_oem(p.IPN) == normalized or normalized in self.normalize_oem(p.IPN):
                if p.id not in seen:
                    seen.add(p.id)
                    results.append({
                        'product': ProductListSerializer(p).data,
                        'match_type': 'exact' if self.normalize_oem(p.IPN) == normalized else 'partial',
                        'matched_number': p.IPN,
                        'matched_brand': p.brand,
                        'confidence': 1.0 if self.normalize_oem(p.IPN) == normalized else 0.8,
                    })

        # Search in cross-references
        xrefs = OemCrossReference.objects.filter(tenant=tenant).select_related('product')
        for xref in xrefs.iterator():
            norm_xref = self.normalize_oem(xref.oem_number)
            if norm_xref == normalized or normalized in norm_xref:
                if xref.product_id not in seen:
                    seen.add(xref.product_id)
                    results.append({
                        'product': ProductListSerializer(xref.product).data,
                        'match_type': 'cross_reference',
                        'matched_number': xref.oem_number,
                        'matched_brand': xref.brand,
                        'confidence': 0.95 if norm_xref == normalized else 0.7,
                    })

        results.sort(key=lambda r: -r['confidence'])
        return Response(results[:20])


# ──────────────────────────────────────────────────────────────
# Feature 11: Dynamic Price Optimization
# ──────────────────────────────────────────────────────────────

class PriceOptimizationView(APIView):
    """Analyzes demand, stock levels, and margins to suggest optimal prices.

    GET /api/ai/price-optimization/
    """

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response([], status=status.HTTP_403_FORBIDDEN)

        cutoff = timezone.now() - timedelta(days=90)

        # Get demand data
        demand_data = StockMovement.objects.filter(
            tenant=tenant, type='OUT', created_at__gte=cutoff,
        ).values('product_id').annotate(
            total_sold=Sum('quantity'),
        )

        demand_map = {d['product_id']: d['total_sold'] for d in demand_data}

        products = Product.objects.filter(
            tenant=tenant, status='active',
        ).exclude(sale_price=0)

        recommendations = []
        for product in products:
            sold = demand_map.get(product.id, 0)
            stock = product.total_in_stock
            purchase = float(product.purchase_price) or 0.01
            sale = float(product.sale_price) or 0.01
            current_margin = ((sale - purchase) / purchase) * 100

            # Demand score: high demand + low stock = increase price
            demand_score = sold / 90  # daily sales
            stock_days = stock / demand_score if demand_score > 0 else 999

            # Recommendation logic
            if demand_score > 2 and stock_days < 14:
                # High demand, low stock → raise price
                suggested = round(sale * 1.10, 2)
                reason = 'Hohe Nachfrage + niedrige Verfügbarkeit'
                action = 'increase'
            elif demand_score < 0.1 and stock > product.minimum_stock * 3:
                # Low demand, high stock → lower price
                suggested = round(sale * 0.90, 2)
                reason = 'Langsame Dreher — Bestand reduzieren'
                action = 'decrease'
            elif current_margin < 15:
                # Margin too low
                suggested = round(purchase * 1.25, 2)
                reason = f'Marge nur {current_margin:.0f}% — unter Zielwert'
                action = 'increase'
            else:
                continue

            new_margin = ((suggested - purchase) / purchase) * 100

            recommendations.append({
                'product': ProductListSerializer(product).data,
                'current_price': sale,
                'suggested_price': suggested,
                'price_change_pct': round(((suggested - sale) / sale) * 100, 1),
                'current_margin_pct': round(current_margin, 1),
                'new_margin_pct': round(new_margin, 1),
                'daily_demand': round(demand_score, 2),
                'stock_days_remaining': round(stock_days, 0),
                'reason': reason,
                'action': action,
            })

        recommendations.sort(key=lambda r: abs(r['price_change_pct']), reverse=True)
        return Response(recommendations[:50])


# ──────────────────────────────────────────────────────────────
# Feature 13: Anomaly Detection
# ──────────────────────────────────────────────────────────────

class AnomalyDetectionView(APIView):
    """Detects unusual stock movements that deviate from historical patterns.

    GET /api/ai/anomalies/
    Query params:
        - days: lookback period (default 7)
        - threshold: deviation multiplier (default 3.0)
    """

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response([], status=status.HTTP_403_FORBIDDEN)

        days = int(request.query_params.get('days', 7))
        threshold = float(request.query_params.get('threshold', 3.0))
        recent_cutoff = timezone.now() - timedelta(days=days)
        historical_cutoff = timezone.now() - timedelta(days=90)

        # Get historical daily averages per product/type
        historical = StockMovement.objects.filter(
            tenant=tenant, created_at__gte=historical_cutoff, created_at__lt=recent_cutoff,
        ).values('product_id', 'type').annotate(
            total_qty=Sum('quantity'),
            count=Count('id'),
        )

        baselines = {}
        for h in historical:
            key = (h['product_id'], h['type'])
            period_days = (timezone.now() - historical_cutoff).days - days
            baselines[key] = {
                'daily_avg': (h['total_qty'] or 0) / max(period_days, 1),
                'daily_count': h['count'] / max(period_days, 1),
            }

        # Get recent movements
        recent = StockMovement.objects.filter(
            tenant=tenant, created_at__gte=recent_cutoff,
        ).values('product_id', 'type').annotate(
            total_qty=Sum('quantity'),
            count=Count('id'),
        )

        anomalies = []
        for r in recent:
            key = (r['product_id'], r['type'])
            baseline = baselines.get(key)
            if not baseline:
                continue

            daily_avg = baseline['daily_avg']
            recent_daily = (r['total_qty'] or 0) / max(days, 1)

            if daily_avg > 0 and recent_daily > daily_avg * threshold:
                product = Product.objects.filter(id=r['product_id']).first()
                if product:
                    anomalies.append({
                        'product': ProductListSerializer(product).data,
                        'movement_type': r['type'],
                        'recent_daily_qty': round(recent_daily, 1),
                        'historical_daily_avg': round(daily_avg, 1),
                        'deviation_factor': round(recent_daily / daily_avg, 1),
                        'total_qty_recent': r['total_qty'],
                        'severity': 'high' if recent_daily > daily_avg * 5 else 'medium',
                        'possible_causes': self._suggest_causes(r['type'], recent_daily, daily_avg),
                    })

        anomalies.sort(key=lambda a: a['deviation_factor'], reverse=True)
        return Response({
            'period_days': days,
            'threshold': threshold,
            'anomalies': anomalies,
            'total_anomalies': len(anomalies),
        })

    @staticmethod
    def _suggest_causes(movement_type, recent, historical):
        """Generate possible explanations for the anomaly."""
        ratio = recent / max(historical, 0.01)
        causes = []
        if movement_type == 'OUT' and ratio > 5:
            causes.append('Mögliche Fehlbuchung oder Diebstahl')
            causes.append('Großbestellung eines Kunden')
        elif movement_type == 'OUT':
            causes.append('Saisonaler Anstieg der Nachfrage')
            causes.append('Marketing-Aktion aktiv')
        elif movement_type == 'IN' and ratio > 5:
            causes.append('Doppelte Lieferung')
            causes.append('Fehlbuchung im Wareneingang')
        return causes


# ──────────────────────────────────────────────────────────────
# Feature 14: Dashboard Briefing / Chat Summary
# ──────────────────────────────────────────────────────────────

class DashboardBriefingView(APIView):
    """Generates a daily briefing for the dealer dashboard.

    GET /api/ai/briefing/
    """

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({}, status=status.HTTP_403_FORBIDDEN)

        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)

        # Orders
        from wws.models import Order
        orders_today = Order.objects.filter(tenant=tenant, created_at__date=today).count()
        orders_week = Order.objects.filter(tenant=tenant, created_at__date__gte=week_ago).count()
        pending_orders = Order.objects.filter(tenant=tenant, status='new').count()

        # Revenue
        from billing.models import Invoice
        revenue_today = Invoice.objects.filter(
            tenant=tenant, status='PAID', issue_date=today,
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        revenue_week = Invoice.objects.filter(
            tenant=tenant, status='PAID', issue_date__gte=week_ago,
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')

        # Stock alerts
        low_stock = Product.objects.filter(
            tenant=tenant, status='active',
        ).annotate(
            stock=Sum('stock_items__quantity')
        ).filter(
            Q(stock__lt=F('minimum_stock')) | Q(stock__isnull=True)
        ).count()

        # Returns
        open_returns = Return.objects.filter(
            tenant=tenant, status__in=['requested', 'approved'],
        ).count()

        # Recent movements
        movements_today = StockMovement.objects.filter(
            tenant=tenant, created_at__date=today,
        ).count()

        # Top products this week
        top_products = StockMovement.objects.filter(
            tenant=tenant, type='OUT', created_at__date__gte=week_ago,
        ).values('product__IPN', 'product__name').annotate(
            total_sold=Sum('quantity'),
        ).order_by('-total_sold')[:5]

        return Response({
            'date': today.isoformat(),
            'orders': {
                'today': orders_today,
                'this_week': orders_week,
                'pending': pending_orders,
            },
            'revenue': {
                'today': float(revenue_today),
                'this_week': float(revenue_week),
            },
            'inventory': {
                'low_stock_alerts': low_stock,
                'movements_today': movements_today,
            },
            'returns': {
                'open': open_returns,
            },
            'top_products': [
                {'ipn': tp['product__IPN'], 'name': tp['product__name'], 'sold': tp['total_sold']}
                for tp in top_products
            ],
            'briefing_text': self._generate_text(
                orders_today, pending_orders, low_stock, open_returns,
                float(revenue_today), top_products,
            ),
        })

    @staticmethod
    def _generate_text(orders, pending, low_stock, returns, revenue, top_products):
        """Generate a human-readable morning briefing."""
        lines = []
        lines.append(f"📋 Heute: {orders} neue Bestellungen, {pending} wartend")

        if revenue > 0:
            lines.append(f"💰 Tagesumsatz: {revenue:.2f}€")

        if low_stock > 0:
            lines.append(f"⚠️ {low_stock} Artikel unter Mindestbestand")

        if returns > 0:
            lines.append(f"📦 {returns} offene Retouren")

        if top_products:
            top = list(top_products)
            if top:
                lines.append(f"🏆 Top-Artikel: {top[0]['product__name']} ({top[0]['total_sold']}x verkauft)")

        return '\n'.join(lines)


# ──────────────────────────────────────────────────────────────
# URL patterns for AI endpoints
# ──────────────────────────────────────────────────────────────

from django.urls import path

ai_urls = [
    path('ai/smart-reorder/', SmartReorderView.as_view(), name='ai-smart-reorder'),
    path('ai/oem-search/', FuzzyOemSearchView.as_view(), name='ai-oem-search'),
    path('ai/price-optimization/', PriceOptimizationView.as_view(), name='ai-price-optimization'),
    path('ai/anomalies/', AnomalyDetectionView.as_view(), name='ai-anomalies'),
    path('ai/briefing/', DashboardBriefingView.as_view(), name='ai-briefing'),
]
