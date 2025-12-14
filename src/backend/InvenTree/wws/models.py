"""Models for WWS domain (orders, offers, suppliers, connections)."""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from tenancy.models import TenantScopedModel
from channels.models import Contact


class MerchantSettings(TenantScopedModel):
    """Merchant (dashboard) preferences."""

    selected_shops = models.JSONField(default=list, blank=True)
    margin_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    price_profiles = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Merchant Settings')
        verbose_name_plural = _('Merchant Settings')
        unique_together = (('tenant',),)

    def __str__(self):
        return f'MerchantSettings {self.tenant_id}'


class Supplier(TenantScopedModel):
    """Supplier data for a tenant."""

    name = models.CharField(max_length=255)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.0'))
    api_type = models.CharField(max_length=50, blank=True, default='')
    meta_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options."""

        verbose_name = _('Supplier')
        verbose_name_plural = _('Suppliers')
        unique_together = ('tenant', 'name')

    def __str__(self):
        """Readable name."""
        return self.name


class WwsConnection(TenantScopedModel):
    """Connection configuration for external WWS sources."""

    class ConnectionType(models.TextChoices):
        """Supported connection types."""

        HTTP_API = 'http_api', 'http_api'
        SCRAPER = 'scraper', 'scraper'
        DEMO = 'demo_wws', 'demo_wws'

    name = models.CharField(max_length=255, blank=True, default='')
    type = models.CharField(max_length=20, choices=ConnectionType.choices)
    base_url = models.URLField(blank=True)
    auth_config_json = models.JSONField(default=dict, blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options."""

        verbose_name = _('WWS Connection')
        verbose_name_plural = _('WWS Connections')

    def __str__(self):
        """Readable name."""
        return f'{self.type} ({self.base_url})'


class Order(TenantScopedModel):
    """Order captured from bot/dashboard."""

    external_ref = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=64, default='new')
    language = models.CharField(max_length=8, blank=True, default='')
    order_data = models.JSONField(default=dict, blank=True)
    vehicle_json = models.JSONField(default=dict, blank=True)
    part_json = models.JSONField(default=dict, blank=True)
    contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders'
    )
    oem = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    currency = models.CharField(max_length=8, default='EUR')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options."""

        verbose_name = _('Order')
        verbose_name_plural = _('Orders')
        ordering = ['-created_at']

    def __str__(self):
        """Readable name."""
        return self.external_ref or f'Order {self.id}'


class Offer(TenantScopedModel):
    """Offer returned by suppliers for an order."""

    class OfferStatus(models.TextChoices):
        """Offer status."""

        DRAFT = 'draft', 'draft'
        PUBLISHED = 'published', 'published'

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='offers', db_index=True
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='offers'
    )
    price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=8, default='EUR')
    availability = models.CharField(max_length=128, blank=True)
    delivery_days = models.IntegerField(null=True, blank=True)
    sku = models.CharField(max_length=100, blank=True)
    product_name = models.CharField(max_length=255, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    product_url = models.URLField(blank=True)
    status = models.CharField(
        max_length=20, choices=OfferStatus.choices, default=OfferStatus.DRAFT
    )
    meta_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options."""

        verbose_name = _('Offer')
        verbose_name_plural = _('Offers')
        ordering = ['-created_at']

    def __str__(self):
        """Readable name."""
        return f'Offer {self.id} for {self.order_id}'


class DealerSupplierSetting(TenantScopedModel):
    """Dashboard-friendly supplier preferences for a tenant."""

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name='dealer_settings'
    )
    enabled = models.BooleanField(default=True)
    priority = models.IntegerField(default=10)
    is_default = models.BooleanField(default=False)

    class Meta:
        """Meta options."""

        unique_together = ('tenant', 'supplier')
        ordering = ['priority']
        verbose_name = _('Dealer Supplier Setting')
        verbose_name_plural = _('Dealer Supplier Settings')
