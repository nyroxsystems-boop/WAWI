"""Serializers for tenancy auth."""

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from tenancy.models import Tenant, TenantUser


class TenantMembershipSerializer(serializers.ModelSerializer):
    """Serializer for user tenant memberships."""

    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    tenant_slug = serializers.CharField(source='tenant.slug', read_only=True)

    class Meta:
        model = TenantUser
        fields = ['id', 'tenant', 'tenant_name', 'tenant_slug', 'role', 'is_active']


class TenantLoginSerializer(serializers.Serializer):
    """Validate dashboard login and tenant selection."""

    email = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    tenant = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        """Validate credentials and tenant membership."""
        identifier = attrs.get('email') or attrs.get('username')
        password = attrs.get('password')
        tenant_ref = attrs.get('tenant')

        if not identifier or not password:
            raise serializers.ValidationError('Email and password are required')

        user = self._authenticate_user(identifier, password)
        if user is None or not user.is_active:
            raise serializers.ValidationError('Invalid credentials')

        membership = self._resolve_membership(user, tenant_ref)
        if membership is None:
            raise serializers.ValidationError('User is not a member of any tenant')

        attrs['user'] = user
        attrs['membership'] = membership
        attrs['tenant'] = membership.tenant
        attrs['role'] = membership.role
        return attrs

    def _authenticate_user(self, identifier, password):
        """Authenticate by username or email."""
        request = self.context.get('request')
        user_model = get_user_model()

        user = authenticate(request=request, username=identifier, password=password)
        if user:
            return user

        # Try email lookup
        email_user = user_model.objects.filter(email__iexact=identifier).first()
        if email_user:
            return authenticate(
                request=request, username=email_user.username, password=password
            )
        return None

    def _resolve_membership(self, user, tenant_ref):
        """Pick the membership to use for issuing a token."""
        memberships = TenantUser.objects.filter(user=user, is_active=True).select_related(
            'tenant'
        )

        if tenant_ref:
            try:
                tenant_id = int(tenant_ref)
                memberships = memberships.filter(tenant_id=tenant_id)
            except (TypeError, ValueError):
                memberships = memberships.filter(tenant__slug=str(tenant_ref))

        return memberships.first()
