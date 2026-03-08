"""Serializers for WWS domain."""

from rest_framework import serializers

from channels.serializers import ContactSerializer
from .models import (
    DealerSupplierSetting, Offer, Order, Product, PurchaseOrder,
    PurchaseOrderItem, StockItem, StockLocation, StockMovement,
    Supplier, SupplierArticle, WwsConnection,
)


# ──────────────────────────────────────────────────────────────
# Supplier
# ──────────────────────────────────────────────────────────────

class SupplierSerializer(serializers.ModelSerializer):
    """Full supplier serializer with new contact fields."""

    active = serializers.BooleanField(source='status', read_only=True)

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'contact_person', 'email', 'phone', 'address',
            'website', 'notes', 'payment_terms', 'rating', 'api_type',
            'status', 'active', 'meta_json', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['active'] = instance.status == 'active'
        return data

    def create(self, validated_data):
        validated_data['tenant'] = self.context.get('tenant')
        return super().create(validated_data)


class DealerSupplierSettingSerializer(serializers.ModelSerializer):
    """Serializer for dealer-supplier mapping."""

    supplier = SupplierSerializer()

    class Meta:
        model = DealerSupplierSetting
        fields = ['supplier', 'enabled', 'priority', 'is_default']


class DealerSupplierSettingUpdateSerializer(serializers.Serializer):
    """Update payload for dealer suppliers."""

    items = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()), allow_empty=True
    )

    def validate(self, attrs):
        items = attrs.get('items', [])
        if not isinstance(items, list):
            raise serializers.ValidationError('items must be a list')
        return attrs


# ──────────────────────────────────────────────────────────────
# Orders & Offers
# ──────────────────────────────────────────────────────────────

class OrderSerializer(serializers.ModelSerializer):
    """Serializer for orders."""

    contact = ContactSerializer(read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'external_ref', 'status', 'language', 'order_data',
            'vehicle_json', 'part_json', 'contact', 'oem', 'notes',
            'total_price', 'currency', 'created_at', 'updated_at',
            'createdAt', 'updatedAt',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'createdAt', 'updatedAt']


class OrderCreateSerializer(serializers.ModelSerializer):
    """Creation serializer for orders."""

    class Meta:
        model = Order
        fields = [
            'external_ref', 'status', 'language', 'order_data',
            'vehicle_json', 'part_json', 'contact', 'oem', 'notes',
            'total_price', 'currency',
        ]

    def create(self, validated_data):
        tenant = self.context['tenant']
        validated_data['tenant'] = tenant
        return super().create(validated_data)


class OfferSerializer(serializers.ModelSerializer):
    """Serializer for offers."""

    supplierName = serializers.CharField(source='supplier.name', read_only=True, default=None)
    shopName = serializers.CharField(source='supplier.name', read_only=True, default=None)
    orderId = serializers.IntegerField(source='order_id', read_only=True)
    basePrice = serializers.DecimalField(source='price', max_digits=12, decimal_places=2, read_only=True)
    finalPrice = serializers.DecimalField(source='price', max_digits=12, decimal_places=2, read_only=True)
    deliveryTimeDays = serializers.IntegerField(source='delivery_days', read_only=True)

    class Meta:
        model = Offer
        fields = [
            'id', 'orderId', 'supplier', 'supplierName', 'shopName',
            'price', 'currency', 'availability', 'delivery_days',
            'deliveryTimeDays', 'sku', 'product_name', 'brand',
            'product_url', 'status', 'meta_json', 'created_at',
            'updated_at', 'basePrice', 'finalPrice',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'supplierName', 'shopName',
            'orderId', 'basePrice', 'finalPrice', 'deliveryTimeDays',
        ]


class OfferCreateSerializer(serializers.ModelSerializer):
    """Create offers for an order."""

    class Meta:
        model = Offer
        fields = [
            'supplier', 'price', 'currency', 'availability', 'delivery_days',
            'sku', 'product_name', 'brand', 'product_url', 'status', 'meta_json',
        ]

    def create(self, validated_data):
        tenant = self.context['tenant']
        order = self.context['order']
        validated_data['tenant'] = tenant
        validated_data['order'] = order
        return super().create(validated_data)


class WwsConnectionSerializer(serializers.ModelSerializer):
    """Serializer for WwsConnection."""

    baseUrl = serializers.URLField(source='base_url', required=False)
    isActive = serializers.BooleanField(source='is_active', required=False)
    authConfig = serializers.JSONField(source='auth_config_json', required=False)
    config = serializers.JSONField(source='config_json', required=False)

    class Meta:
        model = WwsConnection
        fields = [
            'id', 'name', 'type', 'base_url', 'baseUrl',
            'auth_config_json', 'authConfig', 'config_json', 'config',
            'is_active', 'isActive', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['tenant'] = self.context['tenant']
        return super().create(validated_data)


# ──────────────────────────────────────────────────────────────
# Products / Inventory
# ──────────────────────────────────────────────────────────────

class StockByLocationSerializer(serializers.ModelSerializer):
    """Inline stock per location for product detail."""

    location_id = serializers.IntegerField(source='location.id')
    location_name = serializers.CharField(source='location.name')
    location_code = serializers.CharField(source='location.code')

    class Meta:
        model = StockItem
        fields = ['location_id', 'location_name', 'location_code', 'quantity']


class ProductSerializer(serializers.ModelSerializer):
    """Product serializer matching frontend Part interface."""

    total_in_stock = serializers.IntegerField(read_only=True)
    stock_locations = StockByLocationSerializer(source='stock_items', many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'IPN', 'description', 'brand', 'category_name',
            'image', 'minimum_stock', 'article_type', 'status',
            'purchase_price', 'sale_price', 'weight', 'meta_json',
            'total_in_stock', 'stock_locations',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'total_in_stock', 'stock_locations', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['tenant'] = self.context.get('tenant')
        return super().create(validated_data)


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight product serializer for list views."""

    total_in_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'IPN', 'description', 'brand', 'category_name',
            'image', 'minimum_stock', 'article_type', 'status',
            'total_in_stock', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'total_in_stock', 'created_at', 'updated_at']


class StockLocationSerializer(serializers.ModelSerializer):
    """Stock location serializer."""

    current_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockLocation
        fields = ['id', 'name', 'code', 'type', 'capacity', 'current_stock', 'created_at', 'updated_at']
        read_only_fields = ['id', 'current_stock', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['tenant'] = self.context.get('tenant')
        return super().create(validated_data)


class StockMovementSerializer(serializers.ModelSerializer):
    """Stock movement serializer."""

    part_id = serializers.IntegerField(source='product_id')
    part_name = serializers.CharField(source='product.name', read_only=True)
    from_location_name = serializers.CharField(source='from_location.name', read_only=True, default=None)
    to_location_name = serializers.CharField(source='to_location.name', read_only=True, default=None)
    created_by_name = serializers.CharField(source='created_by', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'part_id', 'part_name', 'type', 'quantity',
            'from_location', 'to_location', 'from_location_name', 'to_location_name',
            'reference', 'notes', 'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'part_name', 'from_location_name', 'to_location_name', 'created_by_name', 'created_at']

    def create(self, validated_data):
        validated_data['tenant'] = self.context.get('tenant')
        return super().create(validated_data)


class SupplierArticleSerializer(serializers.ModelSerializer):
    """Supplier article link serializer."""

    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = SupplierArticle
        fields = [
            'id', 'supplier', 'supplier_name', 'product', 'supplier_sku',
            'purchase_price', 'currency', 'lead_time_days',
            'minimum_order_quantity', 'is_preferred', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'supplier_name', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['tenant'] = self.context.get('tenant')
        return super().create(validated_data)


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    """PO line item serializer."""

    part_name = serializers.CharField(source='product.name', read_only=True)
    part_ipn = serializers.CharField(source='product.IPN', read_only=True)
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = [
            'id', 'product', 'part_name', 'part_ipn', 'quantity',
            'unit_price', 'total_price', 'received_quantity',
        ]
        read_only_fields = ['id', 'part_name', 'part_ipn', 'total_price']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    """Purchase order serializer."""

    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items = PurchaseOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'order_number', 'supplier', 'supplier_name', 'status',
            'order_date', 'expected_delivery', 'total_amount', 'currency',
            'notes', 'items', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'supplier_name', 'order_date', 'total_amount', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['tenant'] = self.context.get('tenant')
        return super().create(validated_data)


class PurchaseOrderCreateSerializer(serializers.Serializer):
    """Create PO with nested items."""

    supplier = serializers.IntegerField()
    expected_delivery = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    items = serializers.ListField(child=serializers.DictField(), min_length=1)
