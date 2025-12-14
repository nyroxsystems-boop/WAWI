"""Serializers for WWS domain."""

from rest_framework import serializers

from channels.serializers import ContactSerializer
from tenancy.permissions import IsTenantMember
from .models import DealerSupplierSetting, Offer, Order, Supplier, WwsConnection


class SupplierSerializer(serializers.ModelSerializer):
    """Serializer for supplier."""

    class Meta:
        model = Supplier
        fields = ['id', 'name', 'rating', 'api_type', 'meta_json', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


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
        """Validate items."""
        items = attrs.get('items', [])
        if not isinstance(items, list):
            raise serializers.ValidationError('items must be a list')
        return attrs


class OrderSerializer(serializers.ModelSerializer):
    """Serializer for orders."""

    contact = ContactSerializer(read_only=True)

    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'external_ref',
            'status',
            'language',
            'order_data',
            'vehicle_json',
            'part_json',
            'contact',
            'oem',
            'notes',
            'total_price',
            'currency',
            'created_at',
            'updated_at',
            'createdAt',
            'updatedAt',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'createdAt', 'updatedAt']


class OrderCreateSerializer(serializers.ModelSerializer):
    """Creation serializer for orders."""

    class Meta:
        model = Order
        fields = [
            'external_ref',
            'status',
            'language',
            'order_data',
            'vehicle_json',
            'part_json',
            'contact',
            'oem',
            'notes',
            'total_price',
            'currency',
        ]

    def create(self, validated_data):
        """Assign tenant from context."""
        tenant = self.context['tenant']
        validated_data['tenant'] = tenant
        return super().create(validated_data)


class OfferSerializer(serializers.ModelSerializer):
    """Serializer for offers."""

    supplierName = serializers.CharField(
        source='supplier.name', read_only=True, default=None
    )
    shopName = serializers.CharField(source='supplier.name', read_only=True, default=None)
    orderId = serializers.IntegerField(source='order_id', read_only=True)
    basePrice = serializers.DecimalField(
        source='price', max_digits=12, decimal_places=2, read_only=True
    )
    finalPrice = serializers.DecimalField(
        source='price', max_digits=12, decimal_places=2, read_only=True
    )
    deliveryTimeDays = serializers.IntegerField(source='delivery_days', read_only=True)

    class Meta:
        model = Offer
        fields = [
            'id',
            'orderId',
            'supplier',
            'supplierName',
            'shopName',
            'price',
            'currency',
            'availability',
            'delivery_days',
            'deliveryTimeDays',
            'sku',
            'product_name',
            'brand',
            'product_url',
            'status',
            'meta_json',
            'created_at',
            'updated_at',
            'basePrice',
            'finalPrice',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'supplierName',
            'shopName',
            'orderId',
            'basePrice',
            'finalPrice',
            'deliveryTimeDays',
        ]


class OfferCreateSerializer(serializers.ModelSerializer):
    """Create offers for an order."""

    class Meta:
        model = Offer
        fields = [
            'supplier',
            'price',
            'currency',
            'availability',
            'delivery_days',
            'sku',
            'product_name',
            'brand',
            'product_url',
            'status',
            'meta_json',
        ]

    def create(self, validated_data):
        """Attach tenant and order."""
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
            'id',
            'name',
            'type',
            'base_url',
            'baseUrl',
            'auth_config_json',
            'authConfig',
            'config_json',
            'config',
            'is_active',
            'isActive',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        """Attach tenant."""
        validated_data['tenant'] = self.context['tenant']
        return super().create(validated_data)
