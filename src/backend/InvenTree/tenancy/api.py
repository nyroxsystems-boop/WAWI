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
from tenancy.serializers import TenantLoginSerializer


def _issue_tokens(user, tenant, role, membership):
    """Return refresh/access tokens with tenant claims."""
    refresh = RefreshToken.for_user(user)
    refresh['tenant_id'] = tenant.id
    refresh['role'] = role
    refresh['membership_id'] = membership.id

    access = refresh.access_token
    access['tenant_id'] = tenant.id
    access['role'] = role
    access['membership_id'] = membership.id

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

        refresh, access = _issue_tokens(user, tenant, role, membership)

        log_audit('LOGIN', tenant=tenant, actor=user, metadata={'role': role})

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
            try:
                refresh.blacklist()
            except AttributeError:
                # Blacklist app not installed; nothing else to do
                pass
        except TokenError:
            return Response({'detail': 'Invalid refresh token'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_205_RESET_CONTENT)


auth_api_urls = [
    path('login/', TenantLoginView.as_view(), name='api-auth-login'),
    # Allow slashless variants for compat (dashboard/bot/smoke script).
    path('login', TenantLoginView.as_view(), name='api-auth-login-noslash'),
    path('refresh/', TenantTokenRefreshView.as_view(), name='api-auth-refresh'),
    path('refresh', TenantTokenRefreshView.as_view(), name='api-auth-refresh-noslash'),
    path('logout/', TenantLogoutView.as_view(), name='api-auth-logout'),
    path('logout', TenantLogoutView.as_view(), name='api-auth-logout-noslash'),
]
