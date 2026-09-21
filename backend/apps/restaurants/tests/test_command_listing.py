"""A listagem que desenha a tela inicial do aplicativo do garçom.

O aplicativo abre pedindo `/commands/?status=occupied` e desenha o salão com o
que vier. Duas coisas têm de valer, e as duas falham EM SILÊNCIO se quebrarem:

* o filtro precisa filtrar — o DRF ignora um parâmetro que não está no
  `filterset_fields`, então a tela passaria a mostrar as centenas de comandas
  livres do salão misturadas às poucas em atendimento, sem erro nenhum;
* a contagem e o total pendentes precisam vir na LINHA — sem eles o cartão não
  tem o que mostrar, e buscá-los por comanda custaria uma consulta por cartão.
"""
import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product, ProductCategory
from apps.orders.command_items import launch_item
from apps.restaurants.models import Command


pytestmark = pytest.mark.django_db


@pytest.fixture
def produto(account, restaurant, branch):
    categoria = ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Lanches"
    )
    return Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        category=categoria,
        name="X-Burger",
        internal_code=f"X{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"),
        production_sector=Product.SECTOR_KITCHEN,
    )


def _comanda(account, restaurant, branch, number, **extra):
    return Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number=number,
        **extra,
    )


def _listar_em_uso(client, restaurant):
    resposta = client.get(
        "/api/v1/commands/",
        {"restaurant": str(restaurant.id), "status": "occupied", "page_size": 100},
    )
    assert resposta.status_code == 200, resposta.data
    return resposta.data["results"]


def test_a_tela_inicial_recebe_SO_as_comandas_em_uso(
    admin_client, account, restaurant, branch, manager_user, produto
):
    """O defeito que este teste existe para impedir.

    Sem o filtro valendo, o garçom abriria o aplicativo e veria as comandas
    livres do restaurante inteiro — e a comanda que ele está atendendo ficaria
    perdida no meio delas.
    """
    livre = _comanda(account, restaurant, branch, 300)
    em_uso = _comanda(account, restaurant, branch, 301)
    launch_item(command=em_uso, product=produto, user=manager_user)

    linhas = _listar_em_uso(admin_client, restaurant)

    numeros = {linha["number"] for linha in linhas}
    assert 301 in numeros
    assert 300 not in numeros, "a comanda livre não pertence à tela inicial"
    assert livre.number == 300


def test_a_linha_traz_quanto_a_comanda_deve(
    admin_client, account, restaurant, branch, manager_user, produto
):
    """O cartão mostra "3 itens · R$ X" sem abrir a comanda.

    Buscar isso por cartão faria um salão cheio custar uma consulta por
    comanda só para desenhar a lista.
    """
    comanda = _comanda(account, restaurant, branch, 302)
    for _ in range(3):
        launch_item(command=comanda, product=produto, user=manager_user)

    linha = next(
        linha
        for linha in _listar_em_uso(admin_client, restaurant)
        if linha["number"] == 302
    )

    assert linha["pending_items"] == 3
    assert float(linha["pending_total"]) == pytest.approx(
        float(produto.current_price) * 3
    )


def test_a_comanda_liberada_sai_da_tela_inicial(
    admin_client, account, restaurant, branch, manager_user, produto
):
    """Concluída a última anotação, o cartão está livre — e some da lista.

    É o que impede o cartão reutilizado de reaparecer no salão com a conta do
    cliente anterior.
    """
    from apps.core.tenant import tenant_context
    from apps.orders.command_items import (
        conclude_item,
        free_command_if_empty,
        open_items_of_command,
    )

    comanda = _comanda(account, restaurant, branch, 303)
    launch_item(command=comanda, product=produto, user=manager_user)
    assert {l["number"] for l in _listar_em_uso(admin_client, restaurant)} >= {303}

    # Fora de uma requisição não há middleware para abrir o contexto da conta,
    # e sem ele o gerente por tenant devolve vazio para tudo.
    with tenant_context(account):
        for item in open_items_of_command(comanda.pk):
            conclude_item(item, billed=True)
        free_command_if_empty(comanda)

    numeros = {linha["number"] for linha in _listar_em_uso(admin_client, restaurant)}
    assert 303 not in numeros
