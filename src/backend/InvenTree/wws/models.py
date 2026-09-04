"""Models for WWS domain (orders, offers, suppliers, connections, inventory)."""

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
    contact_person = models.CharField(max_length=255, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=64, blank=True, default='')
    address = models.TextField(blank=True, default='')
    website = models.URLField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    payment_terms = models.CharField(max_length=128, blank=True, default='')
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.0'))
    api_type = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=20, default='active')
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


# ──────────────────────────────────────────────────────────────
# Inventory Management Models
# ──────────────────────────────────────────────────────────────

class Product(TenantScopedModel):
    """Auto parts product / article in the catalogue."""

    class ArticleType(models.TextChoices):
        STANDARD = 'standard', _('Standard')
        SET = 'set', _('Set / Kit')
        DEPOSIT = 'deposit', _('Deposit / Pfand')

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        INACTIVE = 'inactive', _('Inactive')

    name = models.CharField(max_length=255, help_text=_('Product name'))
    IPN = models.CharField(
        max_length=100, db_index=True,
        help_text=_('Internal Part Number / OEM number'),
    )
    description = models.TextField(blank=True, default='')
    brand = models.CharField(max_length=128, blank=True, default='')
    category_name = models.CharField(max_length=128, blank=True, default='')
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    minimum_stock = models.IntegerField(default=0, help_text=_('Minimum stock level before reorder'))
    article_type = models.CharField(
        max_length=20, choices=ArticleType.choices, default=ArticleType.STANDARD,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE,
    )
    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text=_('Default purchase price (EK)'),
    )
    sale_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text=_('Default sale price (VK)'),
    )
    weight = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('0.000'),
        help_text=_('Weight in kg'),
    )
    meta_json = models.JSONField(default=dict, blank=True, help_text=_('Extra metadata'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Product')
        verbose_name_plural = _('Products')
        unique_together = ('tenant', 'IPN')
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'IPN'], name='wws_product_tenant_ipn_idx'),
            models.Index(fields=['tenant', 'brand'], name='wws_product_tenant_brand_idx'),
        ]

    @property
    def total_in_stock(self):
        """Sum of all stock items for this product."""
        return self.stock_items.aggregate(total=models.Sum('quantity'))['total'] or 0

    def __str__(self):
        return f'{self.IPN} — {self.name}'


class StockLocation(TenantScopedModel):
    """Warehouse location / shelf for storing parts."""

    class LocationType(models.TextChoices):
        MAIN = 'main', _('Main Warehouse')
        SHELF = 'shelf', _('Shelf')
        RETURNS = 'returns', _('Returns')
        QUARANTINE = 'quarantine', _('Quarantine')

    name = models.CharField(max_length=255)
    code = models.CharField(
        max_length=32, help_text=_('Location code, e.g. A1-03'),
    )
    type = models.CharField(
        max_length=20, choices=LocationType.choices, default=LocationType.SHELF,
    )
    capacity = models.IntegerField(null=True, blank=True, help_text=_('Max items'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Stock Location')
        verbose_name_plural = _('Stock Locations')
        unique_together = ('tenant', 'code')
        ordering = ['code']

    @property
    def current_stock(self):
        """Total items at this location."""
        return self.stock_items.aggregate(total=models.Sum('quantity'))['total'] or 0

    def __str__(self):
        return f'{self.code} — {self.name}'


class StockItem(TenantScopedModel):
    """Stock quantity for a product at a specific location."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='stock_items', db_index=True,
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.CASCADE, related_name='stock_items', db_index=True,
    )
    quantity = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Stock Item')
        verbose_name_plural = _('Stock Items')
        unique_together = ('tenant', 'product', 'location')
        indexes = [
            models.Index(fields=['tenant', 'product'], name='wws_stockitem_tenant_prod_idx'),
        ]

    def __str__(self):
        return f'{self.product.IPN} @ {self.location.code}: {self.quantity}'


class StockMovement(TenantScopedModel):
    """Record of inventory movement (in, out, transfer, correction)."""

    class MovementType(models.TextChoices):
        IN = 'IN', _('Goods In')
        OUT = 'OUT', _('Goods Out')
        TRANSFER = 'TRANSFER', _('Transfer')
        CORRECTION = 'CORRECTION', _('Correction')

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='movements', db_index=True,
    )
    type = models.CharField(max_length=16, choices=MovementType.choices)
    quantity = models.IntegerField()
    from_location = models.ForeignKey(
        StockLocation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='movements_out',
    )
    to_location = models.ForeignKey(
        StockLocation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='movements_in',
    )
    reference = models.CharField(max_length=128, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.CharField(max_length=128, blank=True, default='system')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Stock Movement')
        verbose_name_plural = _('Stock Movements')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'product'], name='wws_movement_tenant_prod_idx'),
            models.Index(fields=['tenant', 'created_at'], name='wws_movement_tenant_date_idx'),
        ]

    def __str__(self):
        return f'{self.type} {self.quantity}x {self.product.IPN}'


class SupplierArticle(TenantScopedModel):
    """Links a supplier to a product with pricing and lead time."""

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name='articles', db_index=True,
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='supplier_articles', db_index=True,
    )
    supplier_sku = models.CharField(max_length=128, blank=True, default='')
    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
    )
    currency = models.CharField(max_length=8, default='EUR')
    lead_time_days = models.IntegerField(null=True, blank=True)
    minimum_order_quantity = models.IntegerField(default=1)
    is_preferred = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Supplier Article')
        verbose_name_plural = _('Supplier Articles')
        unique_together = ('tenant', 'supplier', 'product')
        ordering = ['supplier__name']

    def __str__(self):
        return f'{self.supplier.name} → {self.product.IPN} ({self.purchase_price} {self.currency})'


class PurchaseOrder(TenantScopedModel):
    """Purchase order sent to a supplier."""

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        SENT = 'sent', _('Sent')
        CONFIRMED = 'confirmed', _('Confirmed')
        RECEIVED = 'received', _('Received')
        CANCELLED = 'cancelled', _('Cancelled')

    order_number = models.CharField(max_length=64, blank=True, db_index=True)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name='purchase_orders', db_index=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT,
    )
    order_date = models.DateField(auto_now_add=True)
    expected_delivery = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
    )
    currency = models.CharField(max_length=8, default='EUR')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Purchase Order')
        verbose_name_plural = _('Purchase Orders')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status'], name='wws_po_tenant_status_idx'),
        ]

    def recalculate_total(self):
        """Recalculate total from line items."""
        total = self.items.aggregate(
            total=models.Sum(models.F('quantity') * models.F('unit_price'))
        )['total'] or Decimal('0.00')
        self.total_amount = total
        self.save(update_fields=['total_amount', 'updated_at'])

    def __str__(self):
        return f'PO-{self.order_number or self.id} ({self.supplier.name})'


class PurchaseOrderItem(TenantScopedModel):
    """Line item within a purchase order."""

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='items', db_index=True,
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='purchase_order_items',
    )
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    received_quantity = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Purchase Order Item')
        verbose_name_plural = _('Purchase Order Items')

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f'{self.quantity}x {self.product.IPN} @ {self.unit_price}'


# ──────────────────────────────────────────────────────────────
# Feature 1: OEM Cross-Reference
# ──────────────────────────────────────────────────────────────

class OemCrossReference(TenantScopedModel):
    """Maps alternative OEM numbers to a product.

    Example: Product IPN=1K0615301AD (VW) has cross-references:
        - TRW → DF6134
        - ATE → 24.0128-0267.1
        - Brembo → 09.C881.11
    """

    class OemType(models.TextChoices):
        OE = 'OE', _('Original Equipment')
        AFTERMARKET = 'AM', _('Aftermarket')
        PARALLEL = 'PARALLEL', _('Parallel OEM')
        CROSS = 'CROSS', _('Generic Cross-Reference')

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='cross_references', db_index=True,
    )
    oem_number = models.CharField(
        max_length=100, db_index=True,
        help_text=_('Alternative OEM / part number'),
    )
    brand = models.CharField(
        max_length=128, blank=True, default='',
        help_text=_('Brand that uses this number, e.g. TRW, ATE, Brembo'),
    )
    oem_type = models.CharField(
        max_length=16, choices=OemType.choices, default=OemType.CROSS,
    )
    source = models.CharField(
        max_length=64, blank=True, default='manual',
        help_text=_('How this reference was added: manual, yq, import, ai'),
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('OEM Cross-Reference')
        verbose_name_plural = _('OEM Cross-References')
        unique_together = ('tenant', 'product', 'oem_number')
        indexes = [
            models.Index(fields=['tenant', 'oem_number'], name='wws_oem_xref_tenant_oem_idx'),
            models.Index(fields=['tenant', 'brand'], name='wws_oem_xref_tenant_brand_idx'),
        ]

    def __str__(self):
        return f'{self.oem_number} ({self.brand}) → {self.product.IPN}'


# ──────────────────────────────────────────────────────────────
# Feature 3: Vehicle Application (KBA/HSN/TSN to Product)
# ──────────────────────────────────────────────────────────────

class VehicleApplication(TenantScopedModel):
    """Maps a product to specific vehicles via KBA numbers or make/model/year."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='vehicle_applications', db_index=True,
    )
    kba_hsn = models.CharField(
        max_length=16, blank=True, default='',
        help_text=_('KBA Herstellerschlüssel (HSN), e.g. 0603'),
    )
    kba_tsn = models.CharField(
        max_length=16, blank=True, default='',
        help_text=_('KBA Typschlüssel (TSN), e.g. BKP'),
    )
    make = models.CharField(max_length=64, blank=True, default='', help_text=_('e.g. VW'))
    model = models.CharField(max_length=128, blank=True, default='', help_text=_('e.g. Golf VII'))
    year_from = models.IntegerField(null=True, blank=True, help_text=_('Production start year'))
    year_to = models.IntegerField(null=True, blank=True, help_text=_('Production end year'))
    engine_code = models.CharField(max_length=32, blank=True, default='', help_text=_('e.g. CRLB'))
    engine_type = models.CharField(max_length=64, blank=True, default='', help_text=_('e.g. 2.0 TDI 150PS'))
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Vehicle Application')
        verbose_name_plural = _('Vehicle Applications')
        indexes = [
            models.Index(fields=['tenant', 'kba_hsn', 'kba_tsn'], name='wws_vehicle_kba_idx'),
            models.Index(fields=['tenant', 'make', 'model'], name='wws_vehicle_make_model_idx'),
        ]

    def __str__(self):
        return f'{self.make} {self.model} ({self.kba_hsn}/{self.kba_tsn}) → {self.product.IPN}'


# ──────────────────────────────────────────────────────────────
# Feature 2: Returns Management
# ──────────────────────────────────────────────────────────────

class Return(TenantScopedModel):
    """Tracks product returns from customers."""

    class ReturnStatus(models.TextChoices):
        REQUESTED = 'requested', _('Requested')
        APPROVED = 'approved', _('Approved')
        RECEIVED = 'received', _('Received')
        INSPECTED = 'inspected', _('Inspected')
        REFUNDED = 'refunded', _('Refunded')
        REJECTED = 'rejected', _('Rejected')

    class ReturnReason(models.TextChoices):
        WRONG_PART = 'wrong_part', _('Wrong Part Delivered')
        DEFECTIVE = 'defective', _('Defective / DOA')
        NOT_NEEDED = 'not_needed', _('No Longer Needed')
        WRONG_ORDER = 'wrong_order', _('Customer Ordered Wrong')
        WARRANTY = 'warranty', _('Warranty Claim')
        OTHER = 'other', _('Other')

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='returns', null=True, blank=True,
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='returns', null=True, blank=True,
    )
    contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='returns',
    )
    quantity = models.IntegerField(default=1)
    reason = models.CharField(
        max_length=32, choices=ReturnReason.choices, default=ReturnReason.OTHER,
    )
    status = models.CharField(
        max_length=32, choices=ReturnStatus.choices, default=ReturnStatus.REQUESTED,
    )
    refund_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
    )
    notes = models.TextField(blank=True, default='')
    location = models.ForeignKey(
        StockLocation, on_delete=models.SET_NULL, null=True, blank=True,
        help_text=_('Return destination (e.g. returns shelf, quarantine)'),
    )
    created_by = models.CharField(max_length=128, blank=True, default='system')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Return')
        verbose_name_plural = _('Returns')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status'], name='wws_return_tenant_status_idx'),
        ]

    def __str__(self):
        part = self.product.IPN if self.product else 'N/A'
        return f'Return #{self.id} — {part} ({self.status})'


# ──────────────────────────────────────────────────────────────
# Feature 5: Price Rules / Quantity-Based Pricing
# ──────────────────────────────────────────────────────────────

class PriceRule(TenantScopedModel):
    """Quantity-based or customer-group-based pricing rules."""

    class PriceProfile(models.TextChoices):
        ENDKUNDE = 'endkunde', _('Endkunde')
        WERKSTATT = 'werkstatt', _('Werkstatt')
        HAENDLER = 'haendler', _('Händler / B2B')
        PARTNER = 'partner', _('Partner')

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='price_rules', db_index=True,
    )
    profile = models.CharField(
        max_length=32, choices=PriceProfile.choices, default=PriceProfile.ENDKUNDE,
    )
    min_quantity = models.IntegerField(default=1, help_text=_('Minimum quantity for this price'))
    price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        help_text=_('Alternative: percentage discount from sale_price'),
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Price Rule')
        verbose_name_plural = _('Price Rules')
        unique_together = ('tenant', 'product', 'profile', 'min_quantity')
        ordering = ['product', 'profile', 'min_quantity']

    def __str__(self):
        return f'{self.product.IPN} — {self.profile} (≥{self.min_quantity}): {self.price}€'


# ──────────────────────────────────────────────────────────────
# Feature 7: Bill of Materials / Stücklisten
# ──────────────────────────────────────────────────────────────

class BomItem(TenantScopedModel):
    """Links a parent product (kit/set) to its component products.

    Example: "Bremsensatz komplett" = Bremsscheibe + Beläge + Sensor
    """

    parent = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='bom_items', db_index=True,
        help_text=_('Parent product (the set/kit)'),
    )
    component = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='used_in_bom', db_index=True,
        help_text=_('Component product'),
    )
    quantity = models.IntegerField(default=1, help_text=_('Quantity of component in the parent'))
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('BOM Item')
        verbose_name_plural = _('BOM Items')
        unique_together = ('tenant', 'parent', 'component')
        ordering = ['parent', 'component']

    def __str__(self):
        return f'{self.parent.IPN} → {self.quantity}x {self.component.IPN}'


# ──────────────────────────────────────────────────────────────
# Feature 8: Supplier Rating / Bewertung
# ──────────────────────────────────────────────────────────────

class SupplierRating(TenantScopedModel):
    """Tracks supplier performance metrics over time."""

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name='ratings', db_index=True,
    )
    period = models.CharField(
        max_length=16, help_text=_('e.g. 2026-Q1 or 2026-03'),
    )
    orders_total = models.IntegerField(default=0)
    orders_on_time = models.IntegerField(default=0)
    orders_late = models.IntegerField(default=0)
    avg_delivery_days = models.DecimalField(
        max_digits=5, decimal_places=1, default=Decimal('0.0'),
    )
    quality_score = models.DecimalField(
        max_digits=3, decimal_places=1, default=Decimal('0.0'),
        help_text=_('Quality score 0-10'),
    )
    return_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        help_text=_('Return rate as percentage'),
    )
    communication_score = models.DecimalField(
        max_digits=3, decimal_places=1, default=Decimal('0.0'),
        help_text=_('Communication responsiveness 0-10'),
    )
    overall_score = models.DecimalField(
        max_digits=3, decimal_places=1, default=Decimal('0.0'),
        help_text=_('Computed overall score 0-10'),
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Supplier Rating')
        verbose_name_plural = _('Supplier Ratings')
        unique_together = ('tenant', 'supplier', 'period')
        ordering = ['-period']
        indexes = [
            models.Index(fields=['tenant', 'supplier', 'period'], name='wws_suprating_idx'),
        ]

    def compute_overall(self):
        """Weighted average: 40% on-time, 30% quality, 20% return, 10% comms."""
        on_time_pct = (self.orders_on_time / max(self.orders_total, 1)) * 10
        return_penalty = max(0, 10 - float(self.return_rate))
        self.overall_score = Decimal(str(round(
            on_time_pct * 0.4 +
            float(self.quality_score) * 0.3 +
            return_penalty * 0.2 +
            float(self.communication_score) * 0.1,
            1
        )))

    def __str__(self):
        return f'{self.supplier.name} — {self.period}: {self.overall_score}/10'
