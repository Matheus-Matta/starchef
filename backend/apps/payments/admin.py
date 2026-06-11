from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin, TenantTabularInline
from apps.payments.models import CashMovement, CashRegister, Payment, PaymentMethod


@admin.register(PaymentMethod)
class PaymentMethodAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "method_type", "is_active")
    list_filter = ("account", "restaurant", "branch", "method_type", "is_active")


@admin.register(Payment)
class PaymentAdmin(TenantModelAdmin):
    list_display = ("order", "account", "payment_method", "amount", "change_amount", "status", "paid_at")
    list_filter = ("account", "restaurant", "branch", "payment_method", "status")


class CashMovementInline(TenantTabularInline):
    model = CashMovement
    extra = 0


@admin.register(CashRegister)
class CashRegisterAdmin(TenantModelAdmin):
    list_display = ("branch", "account", "status", "opened_by", "opened_at", "expected_amount", "actual_amount")
    list_filter = ("account", "restaurant", "branch", "status")
    inlines = [CashMovementInline]


@admin.register(CashMovement)
class CashMovementAdmin(TenantModelAdmin):
    list_display = ("cash_register", "account", "movement_type", "amount", "operator", "created_at")
    list_filter = ("account", "restaurant", "branch", "movement_type")
