"""A recusa precisa ser RECONHECIVEL pelo terminal, nao so legivel.

409 e nao 400 pela mesma razao do `attach-commands`: o corpo do pedido esta
certo. O que barra e o ESTADO — o prato ja foi para a producao ha tempo
demais, ou esta numa coluna do KDS que bloqueia.

Com 400 o PDV trata como erro de preenchimento e reenvia o mesmo corpo para
sempre. Com 409 e um `code` proprio ele reconhece o caso e oferece a
autorizacao do supervisor, que e a saida que existe de proposito.
"""
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import CommandItem, OrderItem
from apps.orders.tests.cenario_cancelamento import item_na_producao
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db

ROTA_PEDIDO = "/api/v1/orders"
ROTA_COMANDA = "/api/v1/commands"


def test_item_de_pedido_fora_do_prazo_responde_409_com_codigo(
    admin_client, restaurant, branch, produto, manager_user
):
    restaurant.item_cancel_window_seconds = 300
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=600)

    resposta = admin_client.delete(
        f"{ROTA_PEDIDO}/{item.order_id}/items/{item.pk}/void/",
        json.dumps({"reason": "cliente desistiu"}),
        content_type="application/json",
    )

    assert resposta.status_code == 409, resposta.content
    corpo = resposta.json()
    # O `code` e o que o terminal le para decidir oferecer o supervisor.
    assert corpo["error"]["code"] == "cancel_blocked"
    assert "prazo para cancelar" in str(corpo["error"]["message"])
    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_SENT


def test_a_senha_de_operacao_no_mesmo_corpo_libera(
    admin_client, restaurant, branch, produto, manager_user
):
    """A saida que o 409 anuncia precisa funcionar no request seguinte."""
    from django.contrib.auth.hashers import make_password

    restaurant.item_cancel_window_seconds = 300
    restaurant.cash_action_password = make_password("1234")
    restaurant.save(
        update_fields=["item_cancel_window_seconds", "cash_action_password"]
    )
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=600)

    resposta = admin_client.delete(
        f"{ROTA_PEDIDO}/{item.order_id}/items/{item.pk}/void/",
        json.dumps({"reason": "prato queimou", "cash_password": "1234"}),
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED


def test_senha_errada_continua_barrando(
    admin_client, restaurant, branch, produto, manager_user
):
    from django.contrib.auth.hashers import make_password

    restaurant.item_cancel_window_seconds = 300
    restaurant.cash_action_password = make_password("1234")
    restaurant.save(
        update_fields=["item_cancel_window_seconds", "cash_action_password"]
    )
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=600)

    resposta = admin_client.delete(
        f"{ROTA_PEDIDO}/{item.order_id}/items/{item.pk}/void/",
        json.dumps({"reason": "tentativa", "cash_password": "9999"}),
        content_type="application/json",
    )

    assert resposta.status_code == 409
    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_SENT


def test_anotacao_de_comanda_fora_do_prazo_tambem_responde_409(
    admin_client, account, restaurant, branch, produto, manager_user
):
    from apps.orders.command_items import launch_item

    restaurant.item_cancel_window_seconds = 300
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    comanda = Command.objects.create(
        account=account, restaurant=restaurant, branch=branch, number=901,
    )
    anotacao = launch_item(command=comanda, product=produto, user=manager_user)
    CommandItem.all_objects.filter(pk=anotacao.pk).update(
        status=CommandItem.STATUS_SENT,
        sent_to_kitchen_at=timezone.now() - timedelta(seconds=600),
    )

    resposta = admin_client.delete(
        f"{ROTA_COMANDA}/{comanda.pk}/items/{anotacao.pk}/void/",
        json.dumps({"reason": "cliente desistiu"}),
        content_type="application/json",
    )

    assert resposta.status_code == 409, resposta.content
    assert resposta.json()["error"]["code"] == "cancel_blocked"


def test_dentro_do_prazo_a_rota_segue_respondendo_normal(
    admin_client, restaurant, branch, produto, manager_user
):
    """A regra nova nao pode mudar o caminho feliz."""
    restaurant.item_cancel_window_seconds = 300
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    item = item_na_producao(restaurant, branch, produto, manager_user, ha_segundos=30)

    resposta = admin_client.delete(
        f"{ROTA_PEDIDO}/{item.order_id}/items/{item.pk}/void/",
        json.dumps({"reason": "cliente desistiu"}),
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    item.refresh_from_db()
    assert item.status == OrderItem.STATUS_CANCELLED
