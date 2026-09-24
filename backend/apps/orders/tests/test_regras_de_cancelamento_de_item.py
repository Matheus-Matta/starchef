"""Ate quando um item que JA esta na producao pode ser cancelado.

Sao duas regras, e as duas dizem a mesma coisa por caminhos diferentes: o
prato ja esta sendo feito, e tira-lo da conta nao desfaz o insumo nem o tempo
do cozinheiro.

NAO se confunde com a carencia. `cancellation_grace_seconds` ATRASA o envio:
dentro dela nada chegou a cozinha e cancelar e de graca. Estas regras comecam
onde aquela termina.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.command_items import launch_item
from apps.orders.command_kitchen import void_command_item
from apps.orders.item_cancellation import CancelamentoBloqueado
from apps.orders.models import CommandItem, Order, OrderItem
from apps.orders.services import add_order_item, create_order, void_order_item
from apps.orders.tests.cenario_cancelamento import item_na_producao
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


# ----------------------------------------------------------- regra do TEMPO

def test_dentro_da_janela_o_item_ainda_pode_ser_cancelado(
    restaurant, branch, produto, manager_user
):
    restaurant.item_cancel_window_seconds = 300
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=60)

    void_order_item(item, manager_user, reason="cliente desistiu")

    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED


def test_passada_a_janela_o_cancelamento_e_recusado(
    restaurant, branch, produto, manager_user
):
    """O que a regra existe para impedir: tirar da conta um prato ja feito."""
    restaurant.item_cancel_window_seconds = 300
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=600)

    with pytest.raises(CancelamentoBloqueado) as recusa:
        void_order_item(item, manager_user, reason="cliente desistiu")

    recado = " ".join(recusa.value.messages)
    # A recusa precisa dizer a REGRA e a SAIDA. "Nao permitido" sozinho manda
    # o operador tentar de novo ate desistir.
    assert "prazo para cancelar" in recado
    assert "supervisor" in recado.lower()
    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_SENT


def test_supervisor_libera_o_que_a_janela_barrou(
    restaurant, branch, produto, manager_user
):
    """O prato queimou. Uma regra sem excecao vira regra contornada por fora."""
    restaurant.item_cancel_window_seconds = 300
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=600)

    void_order_item(item, manager_user, reason="prato queimou", authorized=True)

    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED


def test_janela_desligada_nao_barra_nada(restaurant, branch, produto, manager_user):
    """0 e o padrao: instalacao que ja existe nao muda de comportamento."""
    assert restaurant.item_cancel_window_seconds == 0
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=86400)

    void_order_item(item, manager_user, reason="cancelamento tardio")

    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED


def test_item_que_nao_chegou_a_producao_ignora_a_janela(
    restaurant, branch, produto, manager_user
):
    """Quem manda antes do despacho e a CARENCIA, nao esta regra."""
    restaurant.item_cancel_window_seconds = 1
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    pedido = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER, user=manager_user,
    )
    item = add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    assert item.sent_to_kitchen_at is None

    void_order_item(item, manager_user, reason="errou o pedido")

    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED


# ------------------------------- a anotacao da comanda, que nao entra no KDS

def test_a_anotacao_da_comanda_respeita_a_janela_de_tempo(
    account, restaurant, branch, produto, manager_user
):
    """Ela nao entra no quadro, mas guarda `sent_to_kitchen_at` na mesma base."""
    restaurant.item_cancel_window_seconds = 300
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    comanda = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, number=777,
    )
    anotacao = launch_item(command=comanda, product=produto, user=manager_user)
    CommandItem.all_objects.filter(pk=anotacao.pk).update(
        status=CommandItem.STATUS_SENT,
        sent_to_kitchen_at=timezone.now() - timedelta(seconds=600),
    )
    anotacao.refresh_from_db()

    with pytest.raises(CancelamentoBloqueado):
        void_command_item(anotacao, user=manager_user, reason="cliente desistiu")

    # E o supervisor libera, como no pedido.
    void_command_item(
        anotacao, user=manager_user, reason="prato queimou", authorized=True
    )
    anotacao.refresh_from_db()
    assert anotacao.status == CommandItem.STATUS_CANCELLED
