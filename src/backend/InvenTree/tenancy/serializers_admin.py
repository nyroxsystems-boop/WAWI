"""Admin-focused serializers for tenants and related objects."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
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

    @transaction.atomic
    def create(self, validated_data):
        tenant = self.context['tenant']
        User = get_user_model()
        email = validated_data['user_email'].strip().lower()
        username = validated_data.get('username') or email
        password = validated_data.get('password')

        # Global user identities are shared between tenants. An owner must not
        # reset an existing account's password merely by knowing its email.
        user = User.objects.select_for_update().filter(email__iexact=email).first()
        if user is not None:
            membership = TenantUser.objects.filter(tenant=tenant, user=user).first()
            if membership is None:
                raise serializers.ValidationError({
                    'user_email': (
                        'An account with this email already exists. Use the '
                        'verified invitation flow to add it to another tenant.'
                    )
                })
            if password:
                raise serializers.ValidationError({
                    'password': 'Existing account passwords cannot be changed here.'
                })
            membership.role = validated_data['role']
            membership.is_active = True
            membership.save(update_fields=['role', 'is_active'])
            return membership

        user = User(username=username, email=email, is_active=True)
        if password:
            try:
                validate_password(password, user=user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'password': list(exc.messages)}) from exc
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()

        return TenantUser.objects.create(
            tenant=tenant,
            user=user,
            role=validated_data['role'],
            is_active=True,
        )


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
    """Create a service token bound to the request tenant."""

    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField(), default=list)
    tenant_id = serializers.IntegerField(required=False, write_only=True)

    def validate_scopes(self, scopes):
        """Reject wildcard and unknown capabilities at issuance time."""
        normalized = sorted(set(scopes))
        invalid = [
            scope
            for scope in normalized
            if scope not in ServiceToken.ALLOWED_SCOPES or '*' in scope
        ]
        if invalid:
            raise serializers.ValidationError(
                f'Unknown or wildcard service scopes: {", ".join(invalid)}'
            )
        return normalized

    def validate(self, attrs):
        """Reject an attempted tenant override before creating anything."""
        tenant = self.context.get('tenant')
        requested_tenant_id = attrs.get('tenant_id')
        if (
            tenant is not None
            and requested_tenant_id is not None
            and requested_tenant_id != tenant.id
        ):
            raise serializers.ValidationError({
                'tenant_id': 'Service tokens can only target the current tenant.'
            })
        return super().validate(attrs)

    def create(self, validated_data):
        tenant = self.context.get('tenant')
        if tenant is None:
            raise serializers.ValidationError('Tenant context is required')
        validated_data.pop('tenant_id', None)
        token_raw = ServiceToken.generate_token()
        token = ServiceToken.objects.create(
            name=validated_data['name'],
            token_hash=ServiceToken.hash_token(token_raw),
            scopes=validated_data.get('scopes') or [],
            tenant=tenant,
        )
        token._raw = token_raw  # attach for response
        return token
