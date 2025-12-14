"""API endpoints for WhatsApp channel mapping."""

from django.urls import path

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.context import set_current_tenant
from tenancy.permissions import IsTenantOrServiceToken
from .models import WhatsAppChannel
from .serializers import (
    ContactSerializer,
    ContactUpsertSerializer,
    ConversationSerializer,
    ConversationUpsertSerializer,
)


def _resolve_channel(phone_number_id, tenant=None):
    """Fetch channel ignoring tenant scoping."""
    qs = WhatsAppChannel._base_manager.select_related('tenant').filter(
        phone_number_id=phone_number_id
    )
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    return qs.first()


def _ensure_tenant(request):
    """Ensure request.tenant is set, optionally using phone_number_id."""
    if getattr(request, 'tenant', None):
        return request.tenant

    phone_number_id = request.query_params.get('phone_number_id') or request.data.get(
        'phone_number_id'
    )
    if phone_number_id:
        channel = _resolve_channel(phone_number_id)
        if channel:
            request.tenant = channel.tenant
            set_current_tenant(channel.tenant)
            return channel.tenant

    return None


class WhatsAppResolveView(APIView):
    """Resolve a WhatsApp phone_number_id to tenant info."""

    permission_classes = [IsTenantOrServiceToken]

    def get(self, request):
        """Return channel and tenant mapping."""
        phone_number_id = request.query_params.get('phone_number_id')
        if not phone_number_id:
            return Response(
                {'detail': 'phone_number_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        channel = _resolve_channel(phone_number_id, getattr(request, 'tenant', None))
        if not channel:
            return Response(
                {'detail': 'Channel not found'}, status=status.HTTP_404_NOT_FOUND
            )

        request.tenant = channel.tenant
        set_current_tenant(channel.tenant)
        return Response({'tenant_id': channel.tenant_id, 'channel_id': channel.id})


class ContactUpsertView(APIView):
    """Upsert contact within a tenant."""

    permission_classes = [IsTenantOrServiceToken]

    def post(self, request):
        """Create or update a contact for the current tenant."""
        tenant = _ensure_tenant(request)
        if not tenant:
            return Response(
                {'detail': 'Tenant context required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ContactUpsertSerializer(
            data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)
        contact = serializer.save()
        return Response({'contact': ContactSerializer(contact).data})


class ConversationUpsertView(APIView):
    """Upsert conversation and optional state JSON."""

    permission_classes = [IsTenantOrServiceToken]

    def post(self, request):
        """Create or update a conversation for the given wa_id."""
        tenant = _ensure_tenant(request)
        if not tenant:
            return Response(
                {'detail': 'Tenant context required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ConversationUpsertSerializer(
            data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save()
        return Response({'conversation': ConversationSerializer(conversation).data})


whatsapp_api_urls = [
    path('resolve/', WhatsAppResolveView.as_view(), name='whatsapp-resolve'),
    path('contacts/upsert/', ContactUpsertView.as_view(), name='whatsapp-contact-upsert'),
    path(
        'conversations/upsert/',
        ConversationUpsertView.as_view(),
        name='whatsapp-conversation-upsert',
    ),
]
