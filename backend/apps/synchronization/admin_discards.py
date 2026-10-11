"""O histórico do que este nó ignorou, no Admin — só leitura.

É para conferir e recuperar: o campo `dados` tem o que chegou, como chegou.
Ninguém cria nem edita um descarte; apagar fica para o superusuário.
"""
from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.synchronization.models import SyncDiscard


@admin.register(SyncDiscard)
class SyncDiscardAdmin(ModelAdmin):
    list_display = ("created_at", "motivo", "origem", "entity_type", "entity_id",
                    "versao_recebida", "versao_local", "usuario")
    list_filter = ("motivo", "origem", "entity_type")
    search_fields = ("entity_id", "entity_type")
    readonly_fields = [campo.name for campo in SyncDiscard._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
