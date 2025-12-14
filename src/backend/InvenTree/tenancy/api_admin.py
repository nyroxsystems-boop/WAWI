"""Owner admin endpoints for onboarding tenants and users."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from channels.models import WhatsAppChannel
from tenancy.models import ServiceToken, Tenant, TenantUser
from tenancy.permissions import IsOwner
from tenancy.serializers_admin import (
    ServiceTokenCreateSerializer,
    TenantSerializer,
    TenantUserCreateSerializer,
    WhatsAppChannelCreateSerializer,
)


class TenantAdminViewSet(viewsets.ModelViewSet):
    """Owner-only tenant management."""

    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = TenantSerializer
    queryset = Tenant.objects.all()
    http_method_names = ['get', 'post', 'head', 'options']

    @action(detail=True, methods=['post'], url_path='users')
    def create_user(self, request, pk=None):
        """Create tenant user account."""
        tenant = self.get_object()
        serializer = TenantUserCreateSerializer(
            data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        return Response({
            'id': membership.id,
            'user_id': membership.user_id,
            'tenant_id': tenant.id,
            'role': membership.role,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='whatsapp-channels')
    def create_channel(self, request, pk=None):
        """Assign WhatsApp phone number to tenant."""
        tenant = self.get_object()
        serializer = WhatsAppChannelCreateSerializer(
            data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)
        channel = serializer.save()
        return Response({'id': channel.id, 'tenant_id': tenant.id, 'phone_number_id': channel.phone_number_id}, status=status.HTTP_201_CREATED)


class ServiceTokenViewSet(viewsets.ModelViewSet):
    """Create and list service tokens."""

    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = ServiceTokenCreateSerializer
    queryset = ServiceToken.objects.all()
    http_method_names = ['get', 'post', 'head', 'options']

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        data = [
            {
                'id': t.id,
                'name': t.name,
                'tenant_id': t.tenant_id,
                'scopes': t.scopes,
                'is_active': t.is_active,
            }
            for t in qs
        ]
        return Response(data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={'tenant_override': getattr(request, 'tenant', None)}
        )
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return Response(
            {
                'id': token.id,
                'token': getattr(token, '_raw', None),
                'tenant_id': token.tenant_id,
                'scopes': token.scopes,
            },
            status=status.HTTP_201_CREATED,
        )
