"""A coluna "Status" da lista de comandas ordena TODAS as comandas.

`status` é calculado (ter anotação pendente ou pedido aberto), não coluna do
banco. O ordenador descartava `?ordering=status` em silêncio e o painel tirava
a seta da coluna: "Em uso" ficava espalhado pelas páginas, sem como juntar.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.command_item_launch import launch_item
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexto_tenant(account):
    with tenant_context(account):
        yield account


@pytest.fixture
def comandas(contexto_tenant, account, restaurant, branch, manager_user):
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Prato", internal_code="P1", sale_price=Decimal("25.00"))
    cartoes = {n: Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=n)
               for n in (1, 2, 3, 4)}
    for numero in (2, 4):
        launch_item(command=cartoes[numero], product=produto, user=manager_user)
    return cartoes


def _lista(cliente, consulta):
    resposta = cliente.get(f"/api/v1/commands/?page_size=100&{consulta}")
    assert resposta.status_code == 200, resposta.content
    return resposta.data


def test_ordenar_por_status_junta_as_livres_e_as_em_uso(api_client, contexto_tenant, comandas):
    crescente = [c["status"] for c in _lista(api_client, "ordering=status")["results"]]
    decrescente = [c["status"] for c in _lista(api_client, "ordering=-status")["results"]]

    assert crescente == ["free", "free", "occupied", "occupied"]
    assert decrescente == ["occupied", "occupied", "free", "free"]


def test_a_lista_diz_que_status_ordena(api_client, contexto_tenant, comandas):
    """É o `orderable` que liga a seta da coluna no painel."""
    assert "status" in _lista(api_client, "")["orderable"]


@pytest.mark.parametrize("status, numeros", [("occupied", [2, 4]), ("free", [1, 3])])
def test_filtro_de_status(api_client, contexto_tenant, comandas, status, numeros):
    assert [c["number"] for c in _lista(api_client, f"status={status}")["results"]] == numeros
