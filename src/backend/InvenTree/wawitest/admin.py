from django.contrib import admin

from .models import Document, Job, WawiConfig


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'order_id', 'doc_type', 'version', 'status', 'dedupe_key', 'created_at')
    search_fields = ('order_id', 'doc_type', 'dedupe_key', 'tenant__slug')
    list_filter = ('status', 'doc_type', 'tenant')


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'document', 'status', 'retry_count', 'max_retries', 'created_at')
    search_fields = ('document__order_id', 'tenant__slug')
    list_filter = ('status', 'tenant')


@admin.register(WawiConfig)
class WawiConfigAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'base_url', 'is_active', 'updated_at')
    search_fields = ('tenant__slug', 'base_url')
    list_filter = ('is_active',)
