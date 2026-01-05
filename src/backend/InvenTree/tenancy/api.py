"""API endpoints for tenancy and authentication."""

from django.urls import path

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from audit.utils import log_audit
from tenancy.models import TenantUser, TenantDevice
from tenancy.serializers import TenantLoginSerializer, TenantMembershipSerializer


def _issue_tokens(user, tenant, role, membership, device_id=None):
    """Return refresh/access tokens with tenant claims."""
    refresh = RefreshToken.for_user(user)
    refresh['tenant_id'] = tenant.id
    refresh['role'] = role
    refresh['membership_id'] = membership.id
    if device_id:
        refresh['device_id'] = device_id

    access = refresh.access_token
    access['tenant_id'] = tenant.id
    access['role'] = role
    access['membership_id'] = membership.id
    if device_id:
        access['device_id'] = device_id

    return str(refresh), str(access)


class TenantLoginView(APIView):
    """Issue JWT tokens for dashboard login."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        """Authenticate and return token pair."""
        serializer = TenantLoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        tenant = serializer.validated_data['tenant']
        membership = serializer.validated_data['membership']
        role = serializer.validated_data['role']
        device_id = request.data.get('device_id', 'unknown_device')

        # Enforce device limit
        active_devices = TenantDevice.objects.filter(tenant=tenant)
        active_count = active_devices.count()
        
        # Check if this device is already active
        existing_device = active_devices.filter(user=user, device_id=device_id).first()
        
        if not existing_device and active_count >= tenant.max_devices:
             return Response({
                 'detail': f'Maximale Anzahl an Geräten ({tenant.max_devices}) für diesen Account erreicht. Bitte melden Sie sich auf einem anderen Gerät ab.'
             }, status=status.HTTP_403_FORBIDDEN)

        # Track/Update device
        if existing_device:
            existing_device.save() # Update last_seen
        else:
            TenantDevice.objects.create(
                user=user,
                tenant=tenant,
                device_id=device_id,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                ip_address=request.META.get('REMOTE_ADDR', '')
            )

        refresh, access = _issue_tokens(user, tenant, role, membership, device_id=device_id)

        log_audit('LOGIN', tenant=tenant, actor=user, metadata={'role': role, 'device_id': device_id})

        return Response({
            'access': access,
            'refresh': refresh,
            'tenant': {
                'id': tenant.id,
                'slug': tenant.slug,
                'name': tenant.name,
                'role': role,
            },
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            },
        })


class TenantTokenRefreshView(TokenRefreshView):
    """Refresh access token."""

    permission_classes = [AllowAny]
    authentication_classes = []


class TenantLogoutView(APIView):
    """Optionally blacklist refresh tokens."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        """Invalidate provided refresh token if possible."""
        token = request.data.get('refresh')
        if not token:
            return Response({'detail': 'Refresh token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(token)
            
            # Remove device record
            device_id = refresh.get('device_id')
            tenant_id = refresh.get('tenant_id')
            if device_id and tenant_id:
                TenantDevice.objects.filter(user=request.user, tenant_id=tenant_id, device_id=device_id).delete()

            try:
                refresh.blacklist()
            except AttributeError:
                # Blacklist app not installed; nothing else to do
                pass
        except TokenError:
            return Response({'detail': 'Invalid refresh token'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_205_RESET_CONTENT)


class MyTenantsView(APIView):
    """List tenants for current user."""

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
        memberships = TenantUser.objects.filter(user=request.user, is_active=True).select_related('tenant')
        return Response(TenantMembershipSerializer(memberships, many=True).data)


class MeView(APIView):
    """Return current user and active tenant details."""

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
        
        tenant = getattr(request, 'tenant', None)
        tenant_data = None
        if tenant:
            tenant_data = {
                'id': tenant.id,
                'name': tenant.name,
                'slug': tenant.slug,
            }

        return Response({
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'is_owner': request.user.is_superuser or TenantUser.objects.filter(user=request.user, role='OWNER_ADMIN').exists(),
            },
            'tenant': tenant_data,
            'role': getattr(request, 'tenant_role', None),
        })


class TeamListView(APIView):
    """List all users in the current tenant."""

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response([])
        
        members = TenantUser.objects.filter(tenant=tenant).select_related('user')
        data = [{
            'id': m.user.id,
            'username': m.user.username,
            'email': m.user.email,
            'first_name': m.user.first_name,
            'last_name': m.user.last_name,
            'role': m.role,
            'is_active': m.is_active
        } for m in members]
        
        return Response(data)


auth_api_urls = [
    path('login/', TenantLoginView.as_view(), name='api-auth-login'),
    # Allow slashless variants for compat (dashboard/bot/smoke script).
    path('login', TenantLoginView.as_view(), name='api-auth-login-noslash'),
    path('refresh/', TenantTokenRefreshView.as_view(), name='api-auth-refresh'),
    path('refresh', TenantTokenRefreshView.as_view(), name='api-auth-refresh-noslash'),
    path('logout/', TenantLogoutView.as_view(), name='api-auth-logout'),
    path('logout', TenantLogoutView.as_view(), name='api-auth-logout-noslash'),
    path('me/tenants/', MyTenantsView.as_view(), name='api-auth-my-tenants'),
    path('me/tenants', MyTenantsView.as_view(), name='api-auth-my-tenants-noslash'),
    path('me/', MeView.as_view(), name='api-auth-me'),
    path('me', MeView.as_view(), name='api-auth-me-noslash'),
    path('team/', TeamListView.as_view(), name='api-auth-team'),
    path('team', TeamListView.as_view(), name='api-auth-team-noslash'),
]
