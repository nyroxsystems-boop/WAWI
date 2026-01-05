"""Serializers for WhatsApp channel models."""

from django.utils import timezone
from rest_framework import serializers

from .models import Contact, Conversation


class ContactSerializer(serializers.ModelSerializer):
    """Basic contact serializer."""

    class Meta:
        model = Contact
        fields = ['id', 'wa_id', 'name', 'type', 'tenant']
        read_only_fields = ['tenant']


class ContactUpsertSerializer(serializers.Serializer):
    """Upsert contact payload."""

    wa_id = serializers.CharField()
    name = serializers.CharField(required=False, allow_blank=True)
    type = serializers.ChoiceField(
        choices=Contact.ContactType.choices, default=Contact.ContactType.UNKNOWN
    )

    def save(self, **kwargs):
        """Create or update a contact for the current tenant."""
        tenant = self.context['tenant']
        wa_id = self.validated_data['wa_id']
        defaults = {
            'name': self.validated_data.get('name', ''),
            'type': self.validated_data.get('type', Contact.ContactType.UNKNOWN),
        }
        contact, _ = Contact.objects.update_or_create(
            tenant=tenant, wa_id=wa_id, defaults=defaults
        )
        return contact


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for conversation response."""

    contact = ContactSerializer()

    class Meta:
        model = Conversation
        fields = ['id', 'contact', 'state_json', 'last_message_at']


class ConversationUpsertSerializer(serializers.Serializer):
    """Upsert conversation payload."""

    wa_id = serializers.CharField()
    state_json = serializers.JSONField(required=False)

    def save(self, **kwargs):
        """Create or update a conversation and its contact."""
        tenant = self.context['tenant']
        wa_id = self.validated_data['wa_id']
        contact, _ = Contact.objects.get_or_create(
            tenant=tenant, wa_id=wa_id, defaults={'type': Contact.ContactType.UNKNOWN}
        )

        state = self.validated_data.get('state_json')
        conversation, created = Conversation.objects.get_or_create(
            tenant=tenant, contact=contact
        )

        if state is not None:
            conversation.state_json = state

        if created or state is not None:
            conversation.last_message_at = timezone.now()
            conversation.save()

        return conversation
