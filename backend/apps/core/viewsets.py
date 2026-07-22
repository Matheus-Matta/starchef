"""
Viewsets base reutilizaveis.

Quase todo recurso da API e "tenant-scoped" (isolado por conta/restaurante/filial)
e auditado. Antes, cada viewset repetia a mesma combinacao de mixins:

    class XViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):

Estas classes-base encapsulam essa combinacao — os viewsets das apps passam a
herdar de uma unica classe, sem repetir a lista de mixins nem importa-los.
"""
from rest_framework import viewsets

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin


class BaseTenantViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    """CRUD completo com escopo por tenant + preenchimento/auditoria automaticos.

    - `TenantQuerySetMixin` filtra o queryset pela conta/restaurante/filial do usuario.
    - `AuditCreateUpdateMixin` injeta conta/created_by/updated_by e registra o AuditLog.
    """


class ReadOnlyTenantViewSet(TenantQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """Somente `list`/`retrieve`, com o mesmo isolamento por tenant (sem escrita)."""
