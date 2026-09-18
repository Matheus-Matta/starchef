"""Admin da sincronização: cadastro, progresso e os botões da carga (§14)."""
from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from apps.synchronization.admin_actions import NodeActionsMixin
from apps.synchronization.constants import EventStatus, NodeStatus, RunStatus
from apps.synchronization.models import (
    SyncConflict,
    SyncEnrollmentTicket,
    SyncEvent,
    SyncNode,
    SyncRun,
)

CORES_NO = {
    NodeStatus.ACTIVE: "#16a34a",
    NodeStatus.PENDING: "#ca8a04",
    NodeStatus.OFFLINE: "#6b7280",
    NodeStatus.BLOCKED: "#dc2626",
    NodeStatus.REVOKED: "#dc2626",
}
CORES_EVENTO = {
    EventStatus.ACKNOWLEDGED: "#16a34a",
    EventStatus.APPLIED: "#16a34a",
    EventStatus.DEAD: "#dc2626",
    EventStatus.FAILED: "#ea580c",
}


def _pilula(valor, cores):
    cor = cores.get(valor, "#6b7280")
    return format_html(
        '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;'
        'font-size:11px;font-weight:600">{}</span>', cor, valor,
    )


@admin.register(SyncNode)
class SyncNodeAdmin(NodeActionsMixin, ModelAdmin):
    # `endpoint` é um URLField, e o Django 6 vai trocar o esquema assumido de
    # `http` para `https` quando o texto não traz um. Declarar `https` agora
    # silencia a depreciação e já adota o comportamento futuro — o endpoint da
    # sincronização é sempre `wss://`, então assumir `http` nunca foi útil aqui.
    formfield_overrides = {
        models.URLField: {"assume_scheme": "https"},
    }
    list_display = ("name", "node_type", "account", "estado", "last_seen_at", "fila", "is_self")
    list_filter = ("node_type", "status", "environment", "is_active", "is_self")
    search_fields = ("name", "id", "pair_id", "account__name")
    readonly_fields = (
        "pair_id", "credential_hash", "secret_fingerprint", "encryption_key_id",
        "last_seen_at", "last_sync_at", "last_sent_cursor", "last_received_cursor",
        "sequence_counter", "app_version", "schema_version", "protocol_version",
        "created_at", "updated_at",
    )

    @admin.display(description="Estado")
    def estado(self, obj):
        return _pilula(obj.status, CORES_NO)

    @admin.display(description="Fila")
    def fila(self, obj):
        pendentes = SyncEvent.objects.pending_outbound(obj).count()
        mortos = SyncEvent.objects.filter(source_node=obj, status=EventStatus.DEAD).count()
        if mortos:
            return format_html('{} pendente(s), <b style="color:#dc2626">{} morto(s)</b>',
                               pendentes, mortos)
        return f"{pendentes} pendente(s)"


@admin.register(SyncEvent)
class SyncEventAdmin(ModelAdmin):
    list_display = ("created_at", "entity_type", "entity_id", "operation", "direction",
                    "estado", "attempts", "sequence", "target_node")
    # `target_node` e `source_node` no filtro não são conforto: quando uma loja
    # rematricula, a fila fica apontando para o nó antigo e a única pergunta
    # que importa é "para QUEM estes eventos vão". Sem o filtro, isolá-los no
    # Admin é impossível e sobra apagar tudo.
    list_filter = ("direction", "status", "operation", "entity_type",
                   "target_node", "source_node")
    search_fields = ("event_id", "entity_id", "entity_type", "correlation_id")
    readonly_fields = tuple(f.name for f in SyncEvent._meta.fields)
    date_hierarchy = "created_at"
    actions = ["reprocessar"]

    @admin.display(description="Estado")
    def estado(self, obj):
        return _pilula(obj.status, CORES_EVENTO)

    def has_add_permission(self, request):
        return False

    @admin.action(description="Devolver à fila (reprocessar)")
    def reprocessar(self, request, queryset):
        from apps.synchronization.services import recovery

        total = recovery.requeue(list(queryset))
        self.message_user(request, f"{total} evento(s) devolvidos à fila.")


@admin.register(SyncRun)
class SyncRunAdmin(ModelAdmin):
    list_display = ("created_at", "run_type", "target_node", "estado", "progresso",
                    "current_entity", "initiated_by")
    list_filter = ("run_type", "status")
    search_fields = ("id", "target_node__name")
    readonly_fields = tuple(f.name for f in SyncRun._meta.fields)
    date_hierarchy = "created_at"

    @admin.display(description="Estado")
    def estado(self, obj):
        cor = "#16a34a" if obj.status == RunStatus.COMPLETED else (
            "#dc2626" if obj.status == RunStatus.FAILED else "#2563eb"
        )
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>', cor, obj.status
        )

    @admin.display(description="Progresso")
    def progresso(self, obj):
        return format_html(
            '<div style="background:#e5e7eb;border-radius:4px;width:120px;height:10px">'
            '<div style="background:#2563eb;width:{}%;height:10px;border-radius:4px"></div>'
            "</div><small>{}/{} · {} falha(s)</small>",
            obj.progress_percent, obj.processed_records, obj.total_records, obj.failed_records,
        )

    def has_add_permission(self, request):
        return False


@admin.register(SyncConflict)
class SyncConflictAdmin(ModelAdmin):
    list_display = ("created_at", "entity_type", "entity_id", "status", "resolution",
                    "local_version", "remote_version")
    list_filter = ("status", "resolution", "entity_type")
    search_fields = ("entity_id", "entity_type")
    readonly_fields = ("account", "event", "entity_type", "entity_id", "source_node",
                       "target_node", "local_version", "remote_version", "local_payload",
                       "remote_payload", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(SyncEnrollmentTicket)
class SyncEnrollmentTicketAdmin(ModelAdmin):
    """Só leitura. Emitir é `manage.py sync_issue_ticket`, e há um motivo.

    O código em claro existe uma vez só, na saída do comando. Um formulário de
    criação no Admin teria de exibi-lo numa página que fica no histórico do
    navegador, no log do proxy e, se alguém apertar Ctrl+P por engano, no
    papel. O comando entrega o código ao terminal de quem já está no servidor.
    """

    list_display = ("label", "account", "estado", "created_at", "expires_at", "used_at")
    list_filter = ("account",)
    search_fields = ("label",)
    readonly_fields = ("account", "restaurant", "code_hash", "label", "created_by",
                       "created_at", "expires_at", "used_at", "used_by_node",
                       "used_from_ip")

    @admin.display(description="Estado")
    def estado(self, obj):
        if obj.used_at:
            return "usado"
        return "aberto" if obj.utilizavel else "vencido"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
