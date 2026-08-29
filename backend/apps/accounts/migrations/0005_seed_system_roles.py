"""Provisiona os 4 Perfis de Acesso fixos (Garcom, Caixa, Gerente, Administrador)
em toda conta ja existente. Contas novas passam a recebe-los via signal
(ver apps.accounts.signals.provision_account_system_roles); esta migration
cobre o passado.

Usa os modelos historicos (``apps.get_model``) e so dados puramente Python do
catalogo (``permission_catalog.iter_permissions`` / ``role_catalog.SYSTEM_ROLES``)
— nenhum model "real" e importado, entao a migration continua correta se o
schema evoluir depois dela.
"""
from django.db import migrations


def seed_system_roles(apps, schema_editor):
    from apps.accounts.permission_catalog import iter_permissions
    from apps.accounts.role_catalog import SYSTEM_ROLES

    Account = apps.get_model("accounts", "Account")
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")

    # A migration roda antes do sinal `post_migrate` que sincroniza o
    # catalogo (ele so dispara ao FIM do `migrate`) — garante aqui.
    for code, defaults in iter_permissions():
        Permission.objects.update_or_create(code=code, defaults=defaults)

    permissions_by_code = {p.code: p for p in Permission.objects.all()}

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
    """Sem rollback de dados: os perfis fixos continuam validos voltando a migration anterior."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_focusnfeconfig"),
    ]

    operations = [
        migrations.RunPython(seed_system_roles, noop),
    ]
