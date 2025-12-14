"""Admin-focused serializers for tenants and related objects."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from channels.models import WhatsAppChannel
from tenancy.models import ServiceToken, Tenant, TenantUser


class TenantSerializer(serializers.ModelSerializer):
    """Serializer for tenant creation/list."""

    class Meta:
        model = Tenant
        fields = ['id', 'name', 'slug', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']


class TenantUserCreateSerializer(serializers.Serializer):
    """Create a tenant user binding."""

    user_email = serializers.EmailField()
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=TenantUser.Role.choices)

    def create(self, validated_data):
        tenant = self.context['tenant']
        User = get_user_model()
        email = validated_data['user_email']
        username = validated_data.get('username') or email

        user, _ = User.objects.get_or_create(
            email=email,
            defaults={'username': username, 'is_active': True},
        )
        if validated_data.get('password'):
            user.set_password(validated_data['password'])
            user.save()

        membership, _ = TenantUser.objects.get_or_create(
            tenant=tenant,
            user=user,
            defaults={'role': validated_data['role'], 'is_active': True},
        )
        membership.role = validated_data['role']
        membership.is_active = True
        membership.save()
        return membership


class WhatsAppChannelCreateSerializer(serializers.ModelSerializer):
    """Create WhatsApp channel mapping."""

    class Meta:
        model = WhatsAppChannel
        fields = ['id', 'phone_number_id', 'display_number', 'provider', 'webhook_secret', 'status']
        read_only_fields = ['id']

    def create(self, validated_data):
        validated_data['tenant'] = self.context['tenant']
        return super().create(validated_data)


class ServiceTokenCreateSerializer(serializers.Serializer):
    """Create service token with optional tenant binding."""

    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField(), default=list)
    tenant_id = serializers.IntegerField(required=False, allow_null=True)

    def create(self, validated_data):
        tenant_id = validated_data.get('tenant_id') or None
        tenant = self.context.get('tenant_override') if tenant_id is None else None
        token_raw = ServiceToken.generate_token()
        token = ServiceToken.objects.create(
            name=validated_data['name'],
            token_hash=ServiceToken.hash_token(token_raw),
            scopes=validated_data.get('scopes') or [],
            tenant_id=tenant_id or (tenant.id if tenant else None),
        )
        token._raw = token_raw  # attach for response
        return token
