"""Billing models for invoices and numbering."""

from decimal import Decimal
import logging

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tenancy.models import TenantScopedModel
from channels.models import Contact
from wws.models import Order
from outbox.utils import create_event
from .models_settings import BillingSettings

logger = logging.getLogger('inventree')


class InvoiceSequence(TenantScopedModel):
    """Sequence generator per tenant."""

    prefix = models.CharField(max_length=20, default='RE-')
    next_number = models.IntegerField(default=1)
    padding = models.IntegerField(default=6)
    yearly_reset = models.BooleanField(default=True)
    last_reset_year = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = _('Invoice Sequence')
        verbose_name_plural = _('Invoice Sequences')

    def __str__(self):
        return f'{self.prefix}{self.next_number}'


class Invoice(TenantScopedModel):
    """Invoice model."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'DRAFT'
        ISSUED = 'ISSUED', 'ISSUED'
        SENT = 'SENT', 'SENT'
        PAID = 'PAID', 'PAID'
        CANCELED = 'CANCELED', 'CANCELED'

    invoice_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices'
    )
    contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices'
    )
    issue_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    tax_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=8, default='EUR')
    billing_address_json = models.JSONField(default=dict, blank=True)
    shipping_address_json = models.JSONField(default=dict, blank=True)
    pdf_file = models.FileField(upload_to='invoices/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        ordering = ['-created_at']
        unique_together = ('tenant', 'invoice_number')

    def __str__(self):
        return self.invoice_number or f'Invoice {self.id}'

    def save(self, *args, **kwargs):
        """Prevent changing invoice_number after issuance."""
        if self.pk:
            orig = Invoice.objects.filter(pk=self.pk).first()
            if orig and orig.invoice_number and orig.invoice_number != self.invoice_number:
                raise ValidationError('invoice_number cannot be changed after issuance')
        super().save(*args, **kwargs)

    def recalculate_totals(self):
        """Recompute totals from lines."""
        lines = self.lines.all()
        subtotal = Decimal('0.00')
        tax_total = Decimal('0.00')
        for line in lines:
            subtotal += line.line_total
            tax_total += (line.line_total * Decimal(line.tax_rate)) / Decimal('100.0')
        self.subtotal = subtotal
        self.tax_total = tax_total
        self.total = subtotal + tax_total

    def generate_number(self):
        """Assign invoice number using sequence."""
        with transaction.atomic():
            seq, _ = InvoiceSequence.objects.select_for_update().get_or_create(
                tenant=self.tenant
            )
            year = timezone.now().year
            if seq.yearly_reset and seq.last_reset_year != year:
                seq.next_number = 1
                seq.last_reset_year = year
            number = f"{seq.prefix}{year}-{seq.next_number:0{seq.padding}d}"
            seq.next_number += 1
            seq.save()
        self.invoice_number = number
        self.issue_date = timezone.now().date()

    def generate_pdf(self):
        """Render a simple PDF using WeasyPrint."""
        try:
            from weasyprint import HTML
        except Exception:  # pragma: no cover - fallback if dependency missing
            html = None

        settings_obj = BillingSettings.objects.filter(tenant=self.tenant).first()

        html_content = f"""
        <html>
        <body>
            <h1>Invoice {self.invoice_number or 'Draft'}</h1>
            <p>Status: {self.status}</p>
            <p>Total: {self.total} {self.currency}</p>
            <p>Issue date: {self.issue_date}</p>
            <h3>Seller</h3>
            <p>{settings_obj.company_name if settings_obj else self.tenant.name}</p>
            <p>{settings_obj.address_line1 if settings_obj else ''}</p>
            <p>{(settings_obj.city + ' ' + settings_obj.postal_code) if settings_obj else ''}</p>
            <p>Tax ID: {settings_obj.tax_id if settings_obj else ''}</p>
            <p>IBAN: {settings_obj.iban if settings_obj else ''}</p>
        </body>
        </html>
        """
        if 'HTML' in locals() and HTML:
            pdf_bytes = HTML(string=html_content).write_pdf()
        else:
            pdf_bytes = html_content.encode('utf-8')
        self.pdf_file.save(
            f'invoice-{self.invoice_number or self.id}.pdf',
            ContentFile(pdf_bytes),
            save=False,
        )

    def issue(self):
        """Transition draft to issued and generate artifacts."""
        if self.status != self.Status.DRAFT:
            raise ValueError('Invoice is not in draft state')
        self.generate_number()
        self.recalculate_totals()
        self.status = self.Status.ISSUED
        self.generate_pdf()
        self.save()
        try:
            create_event(
                'INVOICE_ISSUED',
                self.tenant,
                {'invoice_id': self.id, 'invoice_number': self.invoice_number},
            )
        except Exception:  # pragma: no cover - outbox failures should not break issue
            logger.warning('Failed to enqueue INVOICE_ISSUED event', exc_info=True)
        return self

    def send(self):
        """Mark invoice as sent."""
        if self.status not in [self.Status.ISSUED, self.Status.DRAFT]:
            raise ValueError('Invoice must be issued before sending')
        if self.status == self.Status.DRAFT:
            self.issue()
        self.status = self.Status.SENT
        self.save(update_fields=['status'])

    def mark_paid(self):
        """Mark invoice as paid."""
        if self.status in [self.Status.CANCELED]:
            raise ValueError('Cannot pay a canceled invoice')
        self.status = self.Status.PAID
        self.save(update_fields=['status'])

    def cancel(self):
        """Cancel invoice unless paid."""
        if self.status == self.Status.PAID:
            raise ValueError('Cannot cancel a paid invoice')
        self.status = self.Status.CANCELED
        self.save(update_fields=['status'])


class InvoiceLine(TenantScopedModel):
    """Invoice line items."""

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name='lines', db_index=True
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1'))
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00')
    )

    class Meta:
        verbose_name = _('Invoice Line')
        verbose_name_plural = _('Invoice Lines')

    def save(self, *args, **kwargs):
        """Calculate line total."""
        self.line_total = (self.unit_price * self.quantity).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
