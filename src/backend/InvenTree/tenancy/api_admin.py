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
    TenantUserCreateSerializer,
    WhatsAppChannelCreateSerializer,
)
from rest_framework.views import APIView


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
        
        # Enforce user limit
        if tenant.memberships.count() >= tenant.max_users:
            return Response({
                'detail': f'Maximale Anzahl an Benutzern ({tenant.max_users}) für diesen Tenant erreicht.'
            }, status=status.HTTP_400_BAD_REQUEST)

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

    @action(detail=True, methods=['get'], url_path='devices')
    def list_devices(self, request, pk=None):
        """List active devices for tenant."""
        tenant = self.get_object()
        devices = tenant.active_devices.all().select_related('user')
        data = [{
            'id': d.id,
            'user': d.user.username,
            'device_id': d.device_id,
            'last_seen': d.last_seen,
            'ip': d.ip_address,
            'ua': d.user_agent
        } for d in devices]
        return Response(data)

    @action(detail=True, methods=['post'], url_path='remove-device')
    def remove_device(self, request, pk=None):
        """Force logout a device."""
        tenant = self.get_object()
        device_id = request.data.get('device_id')
        tenant.active_devices.filter(device_id=device_id).delete()
        return Response({'status': 'deleted'})


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


class AdminStatsView(APIView):
    """Global oversight stats for Owner Admins."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        tenants = Tenant.objects.all()
        total_tenants = tenants.count()
        total_users = TenantUser.objects.count()
        active_devices = TenantDevice.objects.count()
        
        tenant_stats = []
        for t in tenants:
            tenant_stats.append({
                'id': t.id,
                'name': t.name,
                'slug': t.slug,
                'user_count': t.memberships.count(),
                'max_users': t.max_users,
                'device_count': t.active_devices.count(),
                'max_devices': t.max_devices,
                'is_active': t.is_active,
            })

        return Response({
            'total_tenants': total_tenants,
            'total_users': total_users,
            'total_devices': active_devices,
            'tenants': tenant_stats
        })
