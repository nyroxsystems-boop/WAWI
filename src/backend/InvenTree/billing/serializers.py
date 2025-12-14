"""Serializers for billing domain."""

from rest_framework import serializers

from .models import Invoice, InvoiceLine


class InvoiceLineSerializer(serializers.ModelSerializer):
    """Serializer for invoice lines."""

    class Meta:
        model = InvoiceLine
        fields = ['id', 'description', 'quantity', 'unit_price', 'tax_rate', 'line_total']
        read_only_fields = ['id', 'line_total']

    def create(self, validated_data):
        """Assign tenant from context."""
        validated_data['tenant'] = self.context['tenant']
        validated_data['invoice'] = self.context['invoice']
        return super().create(validated_data)


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for invoice."""

    lines = InvoiceLineSerializer(many=True, required=False)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id',
            'invoice_number',
            'status',
            'order',
            'contact',
            'issue_date',
            'due_date',
            'subtotal',
            'tax_total',
            'total',
            'currency',
            'billing_address_json',
            'shipping_address_json',
            'pdf_file',
            'lines',
            'created_at',
            'updated_at',
            'createdAt',
            'updatedAt',
        ]
        read_only_fields = [
            'id',
            'invoice_number',
            'subtotal',
            'tax_total',
            'total',
            'pdf_file',
            'created_at',
            'updated_at',
            'createdAt',
            'updatedAt',
        ]

    def create(self, validated_data):
        """Handle nested lines and tenant."""
        lines_data = validated_data.pop('lines', [])
        validated_data['tenant'] = self.context['tenant']
        invoice = super().create(validated_data)
        for line in lines_data:
            InvoiceLine.objects.create(
                tenant=self.context['tenant'], invoice=invoice, **line
            )
        invoice.recalculate_totals()
        invoice.save()
        return invoice
