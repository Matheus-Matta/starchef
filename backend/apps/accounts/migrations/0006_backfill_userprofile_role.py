"""Backfill de UserProfile.role a partir do profile_type, antes de remover o
campo e tornar role obrigatorio (proxima migration).

Toda conta ja tem os 4 Perfis fixos provisionados neste ponto (migration
0005_seed_system_roles). O mapeamento reflete o que o resto do sistema ja
tratava como equivalente: "owner" sempre teve os mesmos poderes de "admin"
(is_tenant_admin tratava os dois como iguais) e "kitchen"/"driver" nunca
tiveram efeito real em nenhuma checagem de permissao — caem no cargo mais
baixo (waiter) como default seguro.
"""
from django.db import migrations

PROFILE_TO_ROLE_CODE = {
    "admin": "admin",
    "owner": "admin",
    "manager": "manager",
    "cashier": "cashier",
    "waiter": "waiter",
    "kitchen": "waiter",
    "driver": "waiter",
}


def backfill_role(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    Role = apps.get_model("accounts", "Role")

    roles_by_account = {}
    for profile in UserProfile.objects.filter(role__isnull=True).only("id", "account_id", "profile_type"):
        roles = roles_by_account.get(profile.account_id)
        if roles is None:
            roles = {role.code: role for role in Role.objects.filter(account_id=profile.account_id)}
            roles_by_account[profile.account_id] = roles

        code = PROFILE_TO_ROLE_CODE.get(profile.profile_type, "waiter")
        role = roles.get(code) or next(iter(roles.values()), None)
        if role is not None:
            profile.role_id = role.id
            profile.save(update_fields=["role"])


def noop(apps, schema_editor):
    """Sem rollback de dados: profile_type ainda existe voltando a esta migration."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_seed_system_roles"),
    ]

    operations = [
        migrations.RunPython(backfill_role, noop),
    ]
