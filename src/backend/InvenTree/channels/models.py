"""Models for WhatsApp channel mapping."""

from django.core.exceptions import ValidationError
from django.db import models

from tenancy.models import TenantScopedModel


class WhatsAppChannel(TenantScopedModel):
    """Links a WhatsApp phone number to a tenant."""

    phone_number_id = models.CharField(max_length=64, unique=True)
    display_number = models.CharField(max_length=64, blank=True)
    provider = models.CharField(max_length=50, default='whatsapp')
    webhook_secret = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=32, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options."""

        verbose_name = 'WhatsApp Channel'
        verbose_name_plural = 'WhatsApp Channels'

    def __str__(self):
        """Readable name."""
        return f'{self.display_number or self.phone_number_id} ({self.provider})'


class Contact(TenantScopedModel):
    """WhatsApp contact within a tenant."""

    class ContactType(models.TextChoices):
        """Supported contact types."""

        CUSTOMER = 'CUSTOMER', 'CUSTOMER'
        WORKSHOP = 'WORKSHOP', 'WORKSHOP'
        DEALER = 'DEALER', 'DEALER'
        UNKNOWN = 'UNKNOWN', 'UNKNOWN'

    wa_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200, blank=True)
    type = models.CharField(
        max_length=20, choices=ContactType.choices, default=ContactType.UNKNOWN
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options."""

        unique_together = ('tenant', 'wa_id')
        verbose_name = 'Contact'
        verbose_name_plural = 'Contacts'

    def __str__(self):
        """Readable name."""
        return self.name or self.wa_id


class Conversation(TenantScopedModel):
    """Tracked conversation state for a contact."""

    contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, related_name='conversations'
    )
    state_json = models.JSONField(default=dict, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Meta options."""

        unique_together = ('tenant', 'contact')
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'

    def clean(self):
        """Ensure contact and conversation share tenant."""
        super().clean()
        if self.contact and self.contact.tenant_id != self.tenant_id:
            raise ValidationError({'contact': 'Contact must belong to the same tenant'})

    def __str__(self):
        """Readable name."""
        return f'Conversation with {self.contact}'
