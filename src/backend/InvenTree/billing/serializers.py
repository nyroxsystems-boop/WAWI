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
    
    # Optional simplified fields for easier invoice creation from frontend
    customer_name = serializers.CharField(required=False, write_only=True)
    billing_country = serializers.CharField(required=False, write_only=True)
    notes = serializers.CharField(required=False, write_only=True, allow_blank=True)

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
            'customer_name',
            'billing_country',
            'notes',
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
        
        # Transform simplified fields into billing_address_json
        customer_name = validated_data.pop('customer_name', None)
        billing_country = validated_data.pop('billing_country', None)
        notes = validated_data.pop('notes', None)
        
        if customer_name or billing_country:
            # Only override if not already provided
            if 'billing_address_json' not in validated_data or not validated_data['billing_address_json']:
                validated_data['billing_address_json'] = {}
                if customer_name:
                    validated_data['billing_address_json']['name'] = customer_name
                if billing_country:
                    validated_data['billing_address_json']['country'] = billing_country
        
        # Store notes in billing_address_json for now (could add a dedicated notes field later)
        if notes:
            if 'billing_address_json' not in validated_data:
                validated_data['billing_address_json'] = {}
            validated_data['billing_address_json']['notes'] = notes
        
        validated_data['tenant'] = self.context['tenant']
        invoice = super().create(validated_data)
        for line in lines_data:
            InvoiceLine.objects.create(
                tenant=self.context['tenant'], invoice=invoice, **line
            )
        invoice.recalculate_totals()
        invoice.save()
        return invoice
