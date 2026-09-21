"""O cabeçalho `X-Restaurant-ID` vem do cliente, e precisa ser conferido.

A barra lateral da web manda esse cabeçalho em toda requisição, e estas rotas
o aceitam com precedência sobre o restaurante do perfil — de propósito, porque
é assim que um administrador troca de unidade.

O que faltava era a conferência. Todas as consultas já filtram por
`account=request.account`, então nunca houve vazamento ENTRE contas. O problema
era dentro de uma: um operador preso ao restaurante A podia mandar o id do B e
disparar sincronização com a SEFAZ, mexer no NSU ou listar as notas dele.

`HasTenantAccess` não pega isso porque são `@action`s que não passam por
`get_object()` — a checagem de objeto nunca roda.
"""
import pytest
from rest_framework.exceptions import PermissionDenied

from apps.inbound_nfe.tenant_scope import restaurante_escolhido

pytestmark = pytest.mark.django_db


class _Pedido:
    """O mínimo de uma requisição que o resolvedor lê."""

    def __init__(self, user, *, cabecalho=None, query=None, corpo=None):
        self.user = user
        self.headers = {"X-Restaurant-ID": cabecalho} if cabecalho else {}
        self.query_params = query or {}
        self.data = corpo or {}


@pytest.fixture
def outro_restaurante(account):
    from apps.restaurants.models import Restaurant

    return Restaurant.objects.create(
        account=account, legal_name="Unidade B LTDA", trade_name="Unidade B"
    )


def test_o_proprio_restaurante_passa(manager_user, restaurant):
    pedido = _Pedido(manager_user, cabecalho=str(restaurant.id))
    assert restaurante_escolhido(pedido) == str(restaurant.id)


def test_sem_escolha_cai_no_restaurante_do_perfil(manager_user, restaurant):
    assert restaurante_escolhido(_Pedido(manager_user)) == str(restaurant.id)


def test_restaurante_de_outra_unidade_e_RECUSADO(
    account, restaurant, branch, outro_restaurante,
):
    """O defeito que este arquivo existe para impedir.

    Um operador do restaurante A manda o id do B — da MESMA conta, então os
    filtros por `account` deixariam passar — e dispara a SEFAZ da unidade que
    não é dele.
    """
    from django.contrib.auth import get_user_model

    from apps.accounts.models import UserProfile
    from apps.accounts.role_catalog import ensure_system_roles

    caixa = get_user_model().objects.create_user("caixa-escopo", password="secret123")
    UserProfile.objects.create(
        account=account, user=caixa, role=ensure_system_roles(account)["cashier"],
        restaurant=restaurant, branch=branch,
    )

    with pytest.raises(PermissionDenied):
        restaurante_escolhido(_Pedido(caixa, cabecalho=str(outro_restaurante.id)))


def test_o_administrador_da_conta_troca_de_unidade(admin_user, outro_restaurante):
    """É o que a barra lateral faz, e continua funcionando."""
    pedido = _Pedido(admin_user, cabecalho=str(outro_restaurante.id))
    assert restaurante_escolhido(pedido) == str(outro_restaurante.id)


def test_a_recusa_vale_para_as_tres_portas(
    account, restaurant, branch, outro_restaurante,
):
    """Corpo, query e cabeçalho: não adianta fechar uma e deixar duas abertas."""
    from django.contrib.auth import get_user_model

    from apps.accounts.models import UserProfile
    from apps.accounts.role_catalog import ensure_system_roles

    caixa = get_user_model().objects.create_user("caixa-portas", password="secret123")
    UserProfile.objects.create(
        account=account, user=caixa, role=ensure_system_roles(account)["cashier"],
        restaurant=restaurant, branch=branch,
    )
    alheio = str(outro_restaurante.id)

    for porta in (
        _Pedido(caixa, cabecalho=alheio),
        _Pedido(caixa, query={"restaurant": alheio}),
        _Pedido(caixa, corpo={"restaurant": alheio}),
    ):
        with pytest.raises(PermissionDenied):
            restaurante_escolhido(porta)


def test_sem_perfil_e_sem_escolha_e_a_visao_consolidada(admin_user):
    """`None` é resposta legítima: "Todos os Restaurantes" da conta."""
    assert restaurante_escolhido(_Pedido(admin_user), cair_no_perfil=False) is None
