"""
Viewsets base reutilizaveis.

Quase todo recurso da API e "tenant-scoped" (isolado por conta/restaurante/filial)
e auditado. Antes, cada viewset repetia a mesma combinacao de mixins:

    class XViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):

Estas classes-base encapsulam essa combinacao — os viewsets das apps passam a
herdar de uma unica classe, sem repetir a lista de mixins nem importa-los.
"""
from collections.abc import Mapping

from rest_framework import viewsets
from rest_framework.exceptions import ParseError

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH"})


class JsonObjectBodyMixin:
    """Corpo de escrita precisa ser um OBJETO JSON, nao uma lista nem um escalar.

    O DRF aceita `[1,2,3]` como corpo e entrega a lista em `request.data`. Toda
    view do projeto escreve `request.data.get(...)` — em uma lista isso e
    `AttributeError`, que o handler traduz para 500. Um cliente quebrado (ou um
    teste de fuzzing) derrubava a rota com dois caracteres.

    Barrar aqui, uma vez, e melhor do que espalhar `isinstance` por cada action:
    a regra vale para o CRUD e para toda action customizada que herde desta base.
    Rotas que realmente recebem lista no topo (nao ha nenhuma hoje) podem
    declarar `allows_list_body = True`.
    """

    allows_list_body = False

    def initial(self, request, *args, **kwargs):
        if request.method in WRITE_METHODS and not self.allows_list_body:
            data = request.data
            if data is not None and not isinstance(data, Mapping):
                raise ParseError(
                    "O corpo da requisição precisa ser um objeto JSON com os campos do recurso."
                )
        return super().initial(request, *args, **kwargs)


class BaseTenantViewSet(
    JsonObjectBodyMixin, AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet
):
    """CRUD completo com escopo por tenant + preenchimento/auditoria automaticos.

    - `TenantQuerySetMixin` filtra o queryset pela conta/restaurante/filial do usuario.
    - `AuditCreateUpdateMixin` injeta conta/created_by/updated_by e registra o AuditLog.
    - `JsonObjectBodyMixin` recusa corpo que nao seja objeto JSON.
    """


class ReadOnlyTenantViewSet(TenantQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """Somente `list`/`retrieve`, com o mesmo isolamento por tenant (sem escrita)."""
