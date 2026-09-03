from django.contrib import admin
from apps.core.admin_mixins import TenantModelAdmin
from .models import (
    DFeSyncState,
    DFeDistributionDocument,
    InboundNFe,
    InboundNFeItem,
    SupplierItemMapping,
    DFeGlobalConfig,
)


@admin.action(description="⚡ Zerar Cooldown / Liberar Consulta Imediata na SEFAZ")
def reset_cooldown(modeladmin, request, queryset):
    updated = queryset.update(next_allowed_at=None, last_cstat="138")
    modeladmin.message_user(
        request,
        f"{updated} estado(s) de sincronização liberado(s) com sucesso para consulta imediata."
    )


@admin.register(DFeGlobalConfig)
class DFeGlobalConfigAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "enable_cooldown_blocking",
        "cooldown_interval_minutes",
        "cooldown_no_docs_minutes",
        "updated_at",
    )
    fieldsets = (
        (
            "Regras Gerais de Bloqueio e Cooldown (SEFAZ)",
            {
                "fields": (
                    "enable_cooldown_blocking",
                    "cooldown_interval_minutes",
                    "cooldown_no_docs_minutes",
                    "cooldown_error_minutes",
                ),
                "description": (
                    "Configuração master válida para todas as empresas. "
                    "Se você desmarcar 'Ativar Bloqueio Preventivo de Cooldown', "
                    "o sistema permitirá consultas ilimitadas sem impor janelas de espera."
                ),
            },
        ),
        (
            "Mensagens Exibidas aos Clientes na Tela",
            {
                "fields": (
                    "blocked_message_template",
                    "blocked_cstat_656_message_template",
                ),
                "description": (
                    "Personalize o texto que os operadores verão quando uma consulta for bloqueada. "
                    "Variáveis disponíveis: {time} (horário de liberação), {minutes} (minutos restantes) "
                    "e {interval} (intervalo configurado em minutos)."
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return not DFeGlobalConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DFeSyncState)
class DFeSyncStateAdmin(TenantModelAdmin):
    list_display = (
        "cnpj", "environment", "ult_nsu", "max_nsu",
        "last_cstat", "is_syncing", "next_allowed_at", "last_sync_at"
    )
    list_filter = ("environment", "is_syncing", "branch")
    search_fields = ("cnpj", "last_cstat", "last_reason")
    actions = [reset_cooldown]


@admin.register(DFeDistributionDocument)
class DFeDistributionDocumentAdmin(TenantModelAdmin):
    list_display = (
        "nsu", "schema", "document_type", "access_key",
        "processing_status", "received_at", "processed_at"
    )
    list_filter = ("document_type", "processing_status")
    search_fields = ("nsu", "schema", "access_key")
    readonly_fields = ("xml", "received_at")


@admin.register(InboundNFe)
class InboundNFeAdmin(TenantModelAdmin):
    list_display = (
        "access_key", "number", "supplier_cnpj", "supplier_name",
        "status", "manifestation_status", "issue_date", "total_invoice"
    )
    list_filter = ("status", "manifestation_status", "branch")
    search_fields = ("access_key", "supplier_cnpj", "supplier_name", "number")


@admin.register(InboundNFeItem)
class InboundNFeItemAdmin(TenantModelAdmin):
    list_display = (
        "invoice", "item_number", "description", "ncm",
        "commercial_quantity", "commercial_unit_value", "product_total",
        "ingredient", "product"
    )
    search_fields = ("description", "supplier_code", "ean", "ncm")
    raw_id_fields = ("invoice", "ingredient", "product")


@admin.register(SupplierItemMapping)
class SupplierItemMappingAdmin(TenantModelAdmin):
    list_display = ("supplier_cnpj", "supplier_code", "supplier_ean", "ingredient", "product")
    search_fields = ("supplier_cnpj", "supplier_code", "supplier_ean")
    raw_id_fields = ("ingredient", "product")
