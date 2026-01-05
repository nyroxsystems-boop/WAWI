"""Billing settings per tenant."""

from django.db import models

from tenancy.models import TenantScopedModel


class BillingSettings(TenantScopedModel):
    """Stores billing metadata for invoices."""

    company_name = models.CharField(max_length=255)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=128)
    postal_code = models.CharField(max_length=32)
    country = models.CharField(max_length=64, blank=True, default='')
    tax_id = models.CharField(max_length=64, blank=True, default='')
    iban = models.CharField(max_length=64, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=64, blank=True, default='')

    # Design Settings (Invoice Builder)
    invoice_template = models.CharField(max_length=50, default='clean')
    invoice_color = models.CharField(max_length=20, default='#2563eb')
    invoice_font = models.CharField(max_length=50, default='inter')
    logo_position = models.CharField(max_length=20, default='left')
    number_position = models.CharField(max_length=20, default='right')
    address_layout = models.CharField(max_length=20, default='two-column')
    table_style = models.CharField(max_length=20, default='grid')
    accent_color = models.CharField(max_length=20, default='#f3f4f6')

    class Meta:
        """Meta."""

        verbose_name = 'Billing Settings'
        verbose_name_plural = 'Billing Settings'
