from django import forms
from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.restaurants.models import Branch, Command, DeliveryZone, Deliveryman, Restaurant, Table, TableSector


class RestaurantAdminForm(forms.ModelForm):
    cash_action_password = forms.CharField(
        required=False,
        label="Senha de ações do caixa",
        widget=forms.PasswordInput(render_value=False),
        help_text=(
            "Digite a senha que será usada no caixa (por exemplo, 123). "
            "Não informe nem copie uma hash. Deixe em branco para manter a atual."
        ),
    )

    class Meta:
        model = Restaurant
        fields = "__all__"

    def clean_cash_action_password(self):
        raw_password = self.cleaned_data.get("cash_action_password", "")
        if raw_password or not self.instance.pk:
            return raw_password
        return (
            Restaurant.all_objects.filter(pk=self.instance.pk).values_list("cash_action_password", flat=True).first()
            or ""
        )


@admin.register(Restaurant)
class RestaurantAdmin(TenantModelAdmin):
    form = RestaurantAdminForm
    list_display = ("trade_name", "account", "cnpj", "city", "state", "is_active")
    search_fields = ("trade_name", "legal_name", "cnpj")
    list_filter = ("account", "is_active", "state")


@admin.register(Branch)
class BranchAdmin(TenantModelAdmin):
    list_display = ("name", "account", "restaurant", "cnpj", "is_active")
    search_fields = ("name", "cnpj", "restaurant__trade_name")
    list_filter = ("account", "restaurant", "is_active")


@admin.register(TableSector)
class TableSectorAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "display_order", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")


@admin.register(Table)
class TableAdmin(TenantModelAdmin):
    list_display = ("number", "code", "account", "sector", "branch", "capacity", "status")
    list_filter = ("account", "branch", "status")
    search_fields = ("number", "code")


@admin.register(Command)
class CommandAdmin(TenantModelAdmin):
    list_display = ("number", "code", "account", "restaurant", "customer_name", "status", "is_active")
    list_filter = ("account", "restaurant", "status", "is_active")
    search_fields = ("number", "code", "customer_name")
    ordering = ("restaurant", "number")


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(TenantModelAdmin):
    list_display = (
        "name",
        "account",
        "branch",
        "min_radius_km",
        "max_radius_km",
        "delivery_fee",
        "estimated_minutes",
        "is_active",
    )
    list_filter = ("account", "restaurant", "branch", "is_active")
    search_fields = ("name",)


@admin.register(Deliveryman)
class DeliverymanAdmin(TenantModelAdmin):
    list_display = ("name", "account", "branch", "phone", "vehicle_type", "vehicle_plate", "is_active")
    list_filter = ("account", "restaurant", "branch", "vehicle_type", "is_active")
    search_fields = ("name", "phone", "vehicle_plate")
