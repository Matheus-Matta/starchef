from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin, TenantTabularInline
from apps.payments.models import CashMovement, CashRegister, CashStation, PdvTerminal, Payment, PaymentMethod


@admin.register(CashStation)
class CashStationAdmin(TenantModelAdmin):
    list_display = ("name", "code", "restaurant", "is_active", "cash_limit")
    list_filter = ("account", "restaurant", "is_active")
    search_fields = ("name", "code")
    filter_horizontal = ("operators",)


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


@admin.register(PdvTerminal)
class PdvTerminalAdmin(TenantModelAdmin):
    list_display = ("name", "installation_id", "device_type", "role", "restaurant", "last_seen_at", "is_active")
    list_filter = ("account", "restaurant", "device_type", "role", "is_active")
    search_fields = ("name", "installation_id")
    # A identidade vem do próprio terminal, no primeiro contato: reescrevê-la
    # aqui permitiria "virar" outro terminal e herdar a sessão de caixa dele.
    readonly_fields = ("installation_id", "last_seen_at")


@admin.register(CashRegister)
class CashRegisterAdmin(TenantModelAdmin):
    list_display = (
        "cash_station", "restaurant", "status", "opened_by", "opened_terminal_label",
        "opened_at", "expected_amount", "actual_amount",
    )
    list_filter = ("account", "restaurant", "branch", "status")
    inlines = [CashMovementInline]


@admin.register(CashMovement)
class CashMovementAdmin(TenantModelAdmin):
    list_display = ("cash_register", "account", "movement_type", "amount", "operator", "created_at")
    list_filter = ("account", "restaurant", "branch", "movement_type")
