from apps.accounts.role_catalog import SYSTEM_ROLE_RANKS

# O nível vem do próprio catálogo, não da posição na lista: um perfil novo pode
# ser exibido em qualquer lugar da tela sem que isso o promova na hierarquia.
_ROLE_RANK = dict(SYSTEM_ROLE_RANKS)


def is_tenant_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    if not profile or not profile.role_id:
        return False

    return bool(profile.role.is_account_admin)


def has_role_at_least(user, code):
    """O cargo (Role) do usuário está no nível `code` ou acima.

    Hierarquia: ecommerce < waiter < cashier < manager < admin (os níveis vêm
    de ``role_catalog.SYSTEM_ROLE_RANKS``). O perfil de E-commerce fica no piso
    porque não é um degrau do salão: ele edita o site e nada mais — não pode
    herdar mesa, comanda nem caixa por estar "acima" de alguém."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    if not profile or not profile.role_id:
        return False

    return _ROLE_RANK.get(profile.role.code, -1) >= _ROLE_RANK.get(code, 0)
