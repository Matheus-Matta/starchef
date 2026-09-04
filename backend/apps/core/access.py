from apps.accounts.role_catalog import SYSTEM_ROLE_CODES

_ROLE_RANK = {code: rank for rank, code in enumerate(SYSTEM_ROLE_CODES)}


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
    """O cargo (Role) do usuário está no nível `code` ou acima, na hierarquia
    waiter < cashier < manager < admin (apps.accounts.role_catalog.SYSTEM_ROLE_CODES)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    if not profile or not profile.role_id:
        return False

    return _ROLE_RANK.get(profile.role.code, -1) >= _ROLE_RANK.get(code, 0)
