"""Provisiona a permissão ``scale.operate`` e o Perfil de Acesso "Balança".

Contas novas recebem tudo pelo signal (``provision_account_system_roles``);
esta migration cobre as que já existem — é a mesma rotina da 0009, rodada de
novo, porque o catálogo ganhou um código e um perfil. Reaplicar
``permissions.set(...)`` nos perfis fixos é intencional: o Caixa passa a ter
``scale.operate`` e o Administrador enxerga o código novo.
"""
from django.db import migrations


def seed(apps, schema_editor):
    from apps.accounts.permission_catalog import iter_permissions
    from apps.accounts.role_catalog import SYSTEM_ROLES

    Account = apps.get_model("accounts", "Account")
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")

    for code, defaults in iter_permissions():
        Permission.objects.update_or_create(code=code, defaults=defaults)

    permissions_by_code = {permission.code: permission for permission in Permission.objects.all()}

    for account in Account.objects.all():
        for spec in SYSTEM_ROLES:
            role, _created = Role.objects.update_or_create(
                account=account,
                code=spec["code"],
                defaults={
                    "name": spec["name"],
                    "restaurant": None,
                    "max_discount_percent": spec["max_discount_percent"],
                    "is_account_admin": spec["is_account_admin"],
                    "is_system": True,
                    "is_active": True,
                },
            )
            role.permissions.set(
                [permissions_by_code[code] for code in spec["permissions"] if code in permissions_by_code]
            )


def noop(apps, schema_editor):
    """Sem rollback: remover perfil/permissão órfanaria vínculos de usuário."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_account_local_fiscal_allowed"),
    ]

    operations = [
        migrations.RunPython(seed, noop),
    ]
