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
        color = settings_obj.invoice_color if settings_obj else '#2563eb'
        font = settings_obj.invoice_font if settings_obj else 'Inter, sans-serif'
        accent = settings_obj.accent_color if settings_obj else '#f3f4f6'
        
        logo_pos = settings_obj.logo_position if settings_obj else 'left'
        num_pos = settings_obj.number_position if settings_obj else 'right'
        addr_layout = settings_obj.address_layout if settings_obj else 'two-column'
        table_style = settings_obj.table_style if settings_obj else 'grid'

        html_content = f"""
        <html>
        <head>
            <style>
                @page {{ margin: 2cm; }}
                body {{ 
                    font-family: {font}; 
                    color: #1f2937;
                    line-height: 1.5;
                    font-size: 10pt;
                }}
                .header {{
                    display: flex;
                    flex-direction: {'row' if logo_pos == 'left' and num_pos == 'right' else 'row-reverse' if logo_pos == 'right' and num_pos == 'left' else 'column'};
                    align-items: {'center' if logo_pos == 'center' else 'flex-start'};
                    justify-content: space-between;
                    margin-bottom: 2cm;
                    border-bottom: 2px solid {color};
                    padding-bottom: 20px;
                }}
                .logo-box {{
                    text-align: {logo_pos};
                    margin-bottom: {'20px' if logo_pos == 'center' else '0'};
                }}
                .invoice-title {{
                    font-size: 28pt;
                    color: {color};
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                .details-grid {{
                    display: table;
                    width: 100%;
                    margin-bottom: 1cm;
                }}
                .details-col {{
                    display: table-cell;
                    width: {'50%' if addr_layout == 'two-column' else '100%'};
                    padding-right: 20px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 1cm;
                    border: {'1px solid #e5e7eb' if table_style == 'grid' else 'none'};
                }}
                th {{
                    background-color: {accent if table_style == 'grid' else 'white'};
                    text-align: left;
                    padding: 12px 8px;
                    border-bottom: {'2px solid ' + color if table_style != 'grid' else '1px solid #e5e7eb'};
                    font-weight: bold;
                    text-transform: uppercase;
                    font-size: 9pt;
                }}
                td {{
                    padding: 10px 8px;
                    border-bottom: 1px solid {'#e5e7eb' if table_style != 'minimal' else '#f3f4f6'};
                }}
                .striped tr:nth-child(even) {{
                    background-color: #f9fafb;
                }}
                .totals {{
                    margin-top: 1cm;
                    text-align: right;
                    width: 100%;
                }}
                .totals-table {{
                    display: inline-table;
                    width: 250px;
                }}
                .total-row {{
                    font-size: 14pt;
                    font-weight: bold;
                    color: {color};
                    border-top: 2px solid {color};
                    padding-top: 10px;
                }}
                .footer {{
                    position: fixed;
                    bottom: 0;
                    width: 100%;
                    font-size: 8pt;
                    color: #6b7280;
                    border-top: 1px solid #e5e7eb;
                    padding-top: 10px;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="logo-box">
                    <div style="width: 60px; height: 60px; background: #f3f4f6; border-radius: 8px; display: inline-block; line-height: 60px; text-align: center; color: #9ca3af;">LOGO</div>
                    <div style="margin-top: 10px;">
                        <strong>{settings_obj.company_name if settings_obj else self.tenant.name}</strong><br>
                        <span style="font-size: 9pt; color: #6b7280;">{settings_obj.address_line1 if settings_obj else ''}<br>{settings_obj.city if settings_obj else ''}</span>
                    </div>
                </div>
                <div style="text-align: {num_pos}">
                    <div class="invoice-title">RECHNUNG</div>
                    <span style="font-size: 11pt; font-weight: bold;">{self.invoice_number or 'ENTWURF'}</span><br>
                    Datum: {self.issue_date or timezone.now().date()}
                </div>
            </div>

            <div class="details-grid">
                <div class="details-col">
                    <span style="font-size: 8pt; color: #6b7280; text-transform: uppercase;">Empfänger</span><br>
                    <div style="margin-top: 5px; font-size: 11pt;">
                        <strong>{self.contact.name if self.contact else 'Unbekannt'}</strong><br>
                        {self.contact.wa_id if self.contact else ''}
                    </div>
                </div>
                {f'<div class="details-col" style="text-align: right;"><span style="font-size: 8pt; color: #6b7280; text-transform: uppercase;">Information</span><br><div style="margin-top: 5px;">Fällig am: {self.due_date or "-"}</div></div>' if addr_layout == 'two-column' else ''}
            </div>

            <table class="{'striped' if table_style == 'striped' else ''}">
                <thead>
                    <tr>
                        <th style="width: 40px">Pos</th>
                        <th>Beschreibung</th>
                        <th style="text-align: right">Menge</th>
                        <th style="text-align: right">Einzelpreis</th>
                        <th style="text-align: right">Gesamt</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, line in enumerate(self.lines.all(), 1):
            html_content += f"""
                    <tr>
                        <td>{i}</td>
                        <td>{line.description}</td>
                        <td style="text-align: right">{line.quantity}</td>
                        <td style="text-align: right">{line.unit_price} {self.currency}</td>
                        <td style="text-align: right">{line.line_total} {self.currency}</td>
                    </tr>
            """

        html_content += f"""
                </tbody>
            </table>

            <div class="totals">
                <div class="totals-table">
                    <div style="display: table-row;">
                        <div style="display: table-cell; text-align: left; padding: 5px 0;">Zwischensumme</div>
                        <div style="display: table-cell; text-align: right;">{self.subtotal} {self.currency}</div>
                    </div>
                    <div style="display: table-row;">
                        <div style="display: table-cell; text-align: left; padding: 5px 0;">MwSt (19%)</div>
                        <div style="display: table-cell; text-align: right;">{self.tax_total} {self.currency}</div>
                    </div>
                    <div style="display: table-row;" class="total-row">
                        <div style="display: table-cell; text-align: left; padding: 15px 0;">Gesamtbetrag</div>
                        <div style="display: table-cell; text-align: right;">{self.total} {self.currency}</div>
                    </div>
                </div>
            </div>

            <div class="footer">
                <strong>{settings_obj.company_name if settings_obj else self.tenant.name}</strong><br>
                {settings_obj.address_line1 if settings_obj else ''} · {settings_obj.postal_code if settings_obj else ''} {settings_obj.city if settings_obj else ''} · {settings_obj.country if settings_obj else ''}<br>
                USt-IdNr: {settings_obj.tax_id if settings_obj else ''} · IBAN: {settings_obj.iban if settings_obj else ''} · Email: {settings_obj.email if settings_obj else ''}
            </div>
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
