"""Item parado numa coluna do KDS que barra cancelamento.

E a regra do cozinheiro: depois que o prato entrou na chapa, tira-lo da conta
nao desfaz o insumo nem o tempo. A coluna diz onde ele esta; o flag da coluna
diz se dali ainda da para voltar atras.

A anotacao de comanda nao entra aqui porque ela nao entra no quadro — para ela
vale so a regra de tempo, em `test_regras_de_cancelamento_de_item.py`.
"""
import pytest

from apps.kitchen.models import KdsColumn, KdsItemPosition, KdsStation
from apps.orders.item_cancellation import CancelamentoBloqueado
from apps.orders.models import OrderItem
from apps.orders.services import void_order_item
from apps.orders.tests.cenario_cancelamento import item_na_producao

pytestmark = pytest.mark.django_db


# --------------------------------------------------- regra da COLUNA do KDS

def _posicionar(account, restaurant, branch, item, *, bloqueia):
    """Poe o item numa coluna do KDS.

    So a ESTACAO tem restaurante e filial; coluna e posicao pendem dela.
    """
    estacao = KdsStation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Chapa",
    )
    coluna = KdsColumn.objects.create(
        account=account, station=estacao, name="Em preparo",
        blocks_cancel=bloqueia,
    )
    KdsItemPosition.objects.create(
        account=account, station=estacao, item=item, column=coluna,
    )
    return coluna


def test_coluna_que_bloqueia_recusa_o_cancelamento(
    account, restaurant, branch, produto, manager_user
):
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=10)
    _posicionar(account, restaurant, branch, item, bloqueia=True)

    with pytest.raises(CancelamentoBloqueado) as recusa:
        void_order_item(item, manager_user, reason="cliente desistiu")

    recado = " ".join(recusa.value.messages)
    # Dizer QUAL coluna e QUAL estacao: o operador precisa saber onde o prato
    # esta para decidir se chama o supervisor ou espera.
    assert "Em preparo" in recado
    assert "Chapa" in recado


def test_coluna_que_nao_bloqueia_deixa_passar(
    account, restaurant, branch, produto, manager_user
):
    """Coluna nasce DESLIGADA: criar coluna no meio do almoco nao tranca nada."""
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=10)
    coluna = _posicionar(account, restaurant, branch, item, bloqueia=False)
    assert coluna.blocks_cancel is False

    void_order_item(item, manager_user, reason="cliente desistiu")

    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED


def test_supervisor_libera_o_que_a_coluna_barrou(
    account, restaurant, branch, produto, manager_user
):
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=10)
    _posicionar(account, restaurant, branch, item, bloqueia=True)

    void_order_item(item, manager_user, reason="caiu no chao", authorized=True)

    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED
