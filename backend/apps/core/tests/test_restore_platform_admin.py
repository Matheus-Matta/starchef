"""Comando de resgate: devolve staff/superuser e o vínculo de conta.

Cenário real: os flags do usuário foram removidos no /admin e o perfil que o
ligava à conta inicial foi excluído — a pessoa perde o /admin (precisa de
is_staff) e o app (a API exige conta vinculada).
"""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Account, UserProfile

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def dono(account, restaurant, branch):
    """Superadmin da conta inicial, depois 'quebrado': sem flags e sem perfil."""
    user = User.objects.create_user(username="dono", password="x", email="dono@test.com")
    profile = UserProfile.objects.create(
        account=account, user=user, profile_type=UserProfile.PROFILE_ADMIN, restaurant=restaurant, branch=branch
    )
    profile.delete()  # soft delete — foi o que "removeu o superadmin da conta"
    user.is_staff = False
    user.is_superuser = False
    user.save(update_fields=["is_staff", "is_superuser"])
    return user


def test_restaura_flags_e_vinculo_de_conta(dono, account, restaurant, branch):
    call_command("restore_platform_admin", "--user-id", str(dono.pk))

    dono.refresh_from_db()
    assert dono.is_staff and dono.is_superuser and dono.is_active

    profile = UserProfile.all_objects.get(user=dono)
    assert profile.deleted_at is None
    assert profile.is_active
    assert profile.account_id == account.id
    assert profile.profile_type == UserProfile.PROFILE_ADMIN
    assert profile.restaurant_id == restaurant.id
    assert profile.branch_id == branch.id


def test_cria_perfil_quando_usuario_nao_tem_nenhum(account, restaurant, branch):
    root = User.objects.create_superuser(username="root", password="x", email="root@test.com")

    call_command("restore_platform_admin", "--username", "root")

    profile = UserProfile.all_objects.get(user=root)
    assert profile.account_id == account.id
    assert profile.restaurant_id == restaurant.id


def test_dry_run_nao_altera_nada(dono):
    call_command("restore_platform_admin", "--user-id", str(dono.pk), "--dry-run")

    dono.refresh_from_db()
    assert not dono.is_staff and not dono.is_superuser
    assert UserProfile.all_objects.get(user=dono).deleted_at is not None


def test_escolhe_a_conta_mais_antiga_por_padrao(dono, account):
    Account.objects.create(
        name="Conta Nova", slug=f"nova-{uuid.uuid4().hex[:6]}", status=Account.STATUS_ACTIVE, is_active=True
    )

    call_command("restore_platform_admin", "--user-id", str(dono.pk))

    assert UserProfile.all_objects.get(user=dono).account_id == account.id


def test_slug_inexistente_lista_as_contas_disponiveis(dono, account):
    with pytest.raises(CommandError) as erro:
        call_command("restore_platform_admin", "--user-id", str(dono.pk), "--account-slug", "nao-existe")

    assert account.slug in str(erro.value)


def test_no_superuser_so_restaura_o_vinculo(dono, account):
    call_command("restore_platform_admin", "--user-id", str(dono.pk), "--no-superuser")

    dono.refresh_from_db()
    assert not dono.is_superuser and not dono.is_staff
    assert UserProfile.all_objects.get(user=dono).deleted_at is None
