"""
Quem pode mexer no site.

O restante da API ainda trabalha em cima de papéis; aqui a checagem é por
**código de permissão**, porque o pedido é explícito: editar o site é
privilégio do perfil de E-commerce e do Administrador — ninguém mais, nem o
gerente que administra a operação do salão.

A separação em códigos distintos existe porque as ações têm consequências
diferentes:

- ``storefront.view``    — abrir o editor e olhar;
- ``storefront.edit``    — salvar rascunho, tema, páginas, aplicar modelo;
- ``storefront.publish`` — colocar no ar (é o que o cliente final passa a ver);
- ``storefront.assets``  — enviar/remover imagens;
- ``storefront.domains`` — apontar domínio próprio (mexe em DNS/TLS, e um
  domínio errado tira o site do ar; por padrão fica só com o administrador).
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.access import is_tenant_admin
from apps.core.permissions import effective_permission_codes

PERM_VIEW = "storefront.view"
PERM_EDIT = "storefront.edit"
PERM_PUBLISH = "storefront.publish"
PERM_ASSETS = "storefront.assets"
PERM_DOMAINS = "storefront.domains"

ALL_STOREFRONT_PERMISSIONS = [PERM_VIEW, PERM_EDIT, PERM_PUBLISH, PERM_ASSETS, PERM_DOMAINS]


def has_storefront_permission(user, code):
    """Admin da conta (e superuser) passa direto; os demais precisam do código."""
    if is_tenant_admin(user):
        return True
    codes = effective_permission_codes(user)
    return "*" in codes or code in codes


class StorefrontPermissionMixin:
    """Declara, por viewset, qual código cada tipo de ação exige."""

    storefront_read_permission = PERM_VIEW
    storefront_write_permission = PERM_EDIT
    # Ações extras (`@action`) que exigem um código diferente do de escrita.
    storefront_action_permissions = {}

    def required_storefront_permission(self, request):
        action = getattr(self, "action", None)
        if action and action in self.storefront_action_permissions:
            return self.storefront_action_permissions[action]
        if request.method in SAFE_METHODS:
            return self.storefront_read_permission
        return self.storefront_write_permission


class HasStorefrontPermission(BasePermission):
    """Aplica o código exigido pela view ao usuário autenticado."""

    message = "Você não tem permissão para gerenciar o site do cardápio digital."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        required = None
        if hasattr(view, "required_storefront_permission"):
            required = view.required_storefront_permission(request)
        if not required:
            return True
        return has_storefront_permission(user, required)
