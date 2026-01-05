from django.contrib import admin

from .models import Tenant, TenantUser, ServiceToken


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'status', 'created_at')
    search_fields = ('slug', 'name')
    list_filter = ('status',)


@admin.register(TenantUser)
class TenantUserAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'user', 'role', 'is_active')
    search_fields = ('tenant__slug', 'user__username', 'user__email')
    list_filter = ('role', 'is_active')


@admin.register(ServiceToken)
class ServiceTokenAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'is_active', 'last_used_at')
    search_fields = ('name', 'tenant__slug')
    list_filter = ('is_active',)
