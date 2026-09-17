"""Escopo por conta nas views de sincronização.

Os models daqui não herdam `TenantBaseModel` (eles são infraestrutura, não
cadastro de negócio), então o `TenantQuerySetMixin` do core não serve. O
isolamento é o mesmo, escrito aqui: sem conta resolvida, um não-superusuário
não vê nada — nunca o contrário.
"""


class AccountScopedMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        usuario = self.request.user
        conta_id = self._account_id(self.request)

        if usuario.is_superuser and conta_id is None:
            # O dono da plataforma pode olhar tudo — mas só ele, e só quando
            # não há conta no request.
            return queryset
        if conta_id is None:
            return queryset.none()
        return queryset.filter(account_id=conta_id)

    def _account_id(self, request):
        conta = getattr(request, "account", None)
        if conta is not None:
            return conta.pk
        perfil = getattr(request.user, "profile", None)
        return getattr(perfil, "account_id", None)
