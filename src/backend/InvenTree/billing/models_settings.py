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

    class Meta:
        """Meta."""

        verbose_name = 'Billing Settings'
        verbose_name_plural = 'Billing Settings'
