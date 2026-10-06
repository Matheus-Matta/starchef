"""O perfil "Balança": opera a Balança Rápida, e nada além dela.

É o operador da estação de pesagem do self-service. Ele passa o cartão, o prato
é pesado e o peso entra na comanda. Não abre caixa, não vê pedidos, não cancela
nada e não configura equipamento — por isso é uma especialidade fora da escada
Garçom ⊂ Caixa ⊂ Gerente, como o E-commerce.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.accounts.permission_catalog import ALL_CODES
from apps.accounts.role_catalog import CODE_SCALE, SYSTEM_ROLES, ensure_system_roles
from apps.core.access import has_role_at_least
from apps.core.tenant import tenant_context
from apps.printers.models import Printer, Scale

pytestmark = pytest.mark.django_db


@pytest.fixture
def operador_da_balanca(account, restaurant, branch):
    user = User.objects.create_user(username="balanca", password="x")
    UserProfile.objects.create(
        account=account, user=user, role=ensure_system_roles(account)[CODE_SCALE],
        restaurant=restaurant, branch=branch,
    )
    return user


@pytest.fixture
def cliente(operador_da_balanca):
    client = APIClient()
    token = str(RefreshToken.for_user(operador_da_balanca).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def balanca(account, restaurant, branch):
    with tenant_context(account):
        impressora = Printer.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Balança 1",
        )
        return Scale.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Buffet",
            printer=impressora, weighing_mode=Scale.MODE_COMMAND,
        )


def test_o_perfil_tem_so_a_balanca_e_a_leitura_do_cardapio():
    spec = next(s for s in SYSTEM_ROLES if s["code"] == CODE_SCALE)
    assert spec["name"] == "Balança"
    assert set(spec["permissions"]) == {"scale.operate", "menu.view"}
    assert "scale.operate" in ALL_CODES


def test_o_perfil_fica_abaixo_do_garcom_na_hierarquia(operador_da_balanca):
    """Nada que pede "pelo menos garçom" pode valer para ele."""
    assert not has_role_at_least(operador_da_balanca, "waiter")


def test_o_pdv_recebe_o_perfil_no_login(cliente):
    resposta = cliente.get("/api/v1/auth/me/")

    assert resposta.status_code == 200, resposta.data
    assert resposta.data["profile_type"] == CODE_SCALE


def test_enxerga_balancas_e_impressoras_para_operar(cliente, balanca):
    assert cliente.get("/api/v1/scales/").status_code == 200
    assert cliente.get("/api/v1/printers/").status_code == 200


def test_nao_configura_a_balanca(cliente, balanca):
    """Trocar a impressora da balança é configuração de equipamento (gerente)."""
    resposta = cliente.patch(
        f"/api/v1/scales/{balanca.pk}/", {"printer": None}, format="json"
    )

    assert resposta.status_code == 403


def test_pode_lancar_a_pesagem_na_comanda(operador_da_balanca, balanca):
    """`checkout-command` é o gesto da estação: tirar o pedido da balança."""
    from rest_framework.test import APIRequestFactory

    from apps.core.permissions import CanOperateScale

    pedido = APIRequestFactory().post("/")
    pedido.user = operador_da_balanca

    assert CanOperateScale().has_permission(pedido, view=None)


def test_o_caixa_continua_operando_a_balanca():
    spec = next(s for s in SYSTEM_ROLES if s["code"] == "cashier")
    assert "scale.operate" in spec["permissions"]
