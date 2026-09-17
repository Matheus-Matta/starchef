"""Permissões da API de sincronização.

Duas, e a diferença entre elas importa: ver o estado da fila é rotina de
suporte; disparar uma carga total, revogar um vínculo ou rotacionar credencial
mexe na operação de uma loja inteira.

Os códigos vêm do catálogo do projeto (`accounts.permission_catalog`), não do
sistema de permissões do Django. É uma diferença que já custou um bug: o
`has_perm` do Django consulta `auth_permission`, que este projeto não usa para
autorizar negócio — um administrador de conta nunca teria aquela permissão, e
a API respondia 403 para quem é dono da conta.

O `/admin/` continua usando as permissões do Django, porque é assim que o
Django admin funciona (ver `admin_actions.py`).
"""
from rest_framework.permissions import BasePermission

from apps.core.access import is_tenant_admin
from apps.core.permissions import effective_permission_codes

CODIGO_VER = "sync.view"
CODIGO_GERENCIAR = "sync.manage"


def _tem(usuario, codigo):
    codigos = effective_permission_codes(usuario)
    return "*" in codigos or codigo in codigos


class CanManageSync(BasePermission):
    """Ler nós, fila, cargas e conflitos da própria conta."""

    message = "Você não tem acesso ao gerenciamento de sincronização."

    def has_permission(self, request, view):
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False
        if usuario.is_superuser or is_tenant_admin(usuario):
            return True
        return _tem(usuario, CODIGO_VER)


class CanStartFullSync(BasePermission):
    """Ações que mexem: carga, reprocessamento, revogação, rotação de chave."""

    message = "Somente um administrador com permissão de sincronização pode fazer isso."

    def has_permission(self, request, view):
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False
        if usuario.is_superuser or is_tenant_admin(usuario):
            return True
        return _tem(usuario, CODIGO_GERENCIAR)
