"""Serializers for external sync endpoints."""

from __future__ import annotations

from rest_framework import serializers


class AddressSerializer(serializers.Serializer):
    street = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    zip = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    country = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CustomerSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    address = AddressSerializer(required=False)


class LineSerializer(serializers.Serializer):
    sku = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    oe_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    qty = serializers.IntegerField(min_value=1)
    unit_price = serializers.FloatField()
    tax_rate = serializers.FloatField(required=False, default=0.0)


class ExternalOrderUpsertSerializer(serializers.Serializer):
    status = serializers.CharField(max_length=64)
    version = serializers.IntegerField(min_value=1)
    customer = CustomerSerializer(required=False)
    lines = LineSerializer(many=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ExternalDocumentCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['QUOTE', 'INVOICE'])

