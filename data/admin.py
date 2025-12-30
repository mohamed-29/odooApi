from django.contrib import admin
from .models import xy_account, machine, Order

@admin.register(xy_account)
class XYAccountAdmin(admin.ModelAdmin):
    list_display = ('username', 'shbh', 'userid')
    search_fields = ('username', 'shbh', 'userid')

@admin.register(machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ('name', 'number', 'is_online', 'is_broken', 'last_online', 'last_order', 'last_update')
    list_filter = ('is_online', 'is_broken')
    search_fields = ('name', 'number')
    readonly_fields = ('last_update',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'uuid', 'provider', 'machine', 'product_name',
        'payment_amount', 'payment_time', 'payment_type',
        'payment_status', 'delivery_state', 'sync_status',
        'created_at', 'updated_at'
    )
    list_filter = (
        'provider', 'payment_type', 'payment_status','machine',
        'delivery_state', 'sync_status', 'payment_time', 'updated_at'
    )
    search_fields = (
        'uuid', 'source_order_no', 'machine__name', 'machine__number', 'product_name',
        'external_id'
    )
    date_hierarchy = 'payment_time'
    readonly_fields = (
        'uuid', 'provider', 'source_order_no', 'machine',
        'product_name', 'slot_number', 'payment_amount', 'payment_time',
        'payment_type', 'payment_status', 'delivery_state', 'source_payload',
        'created_at', 'updated_at'
    )
