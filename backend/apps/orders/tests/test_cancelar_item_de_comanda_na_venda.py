"""Cancelar, na tela de venda, um item que veio de comanda.

O item da conta é uma CÓPIA da anotação da comanda, e a produção é lida da
origem. Cancelar só a cópia fechava a anotação no cartão, mas deixava a origem
"enviada" ou "em preparo", sem motivo e sem autor: o histórico da comanda
dizia "encerrado sem cobrança" sem dizer quem nem por quê, e o aviso à
cozinha saía pelo caminho do pedido, que não foi por onde o prato entrou.

Agora o cancelamento vai à ORIGEM, pelo mesmo caminho do cancelamento feito na
comanda, e a linha da conta acompanha.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem, Order, OrderItem
from apps.orders.services import create_order
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def conta_com_comanda(contexto_tenant, account, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio):
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=41)
    anotacao = launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    CommandItem.objects.filter(pk=anotacao.pk).update(
        status=CommandItem.STATUS_PREPARING, sent_to_kitchen_at=timezone.now()
    )
    conta = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, user=manager_user)
    [linha] = attach_commands_to_order(order=conta, command_ids=[comanda.pk], user=manager_user)
    return conta, linha, anotacao, comanda


@pytest.fixture
def avisos(monkeypatch):
    import apps.printers.command_kitchen as pela_comanda
    import apps.printers.services as pelo_pedido

    vistos = {"comanda": 0, "pedido": 0}
    monkeypatch.setattr(pela_comanda, "register_command_item_cancellation_jobs",
                        lambda **kw: vistos.__setitem__("comanda", vistos["comanda"] + 1))
    monkeypatch.setattr(pelo_pedido, "register_kitchen_item_cancellation_jobs",
                        lambda **kw: vistos.__setitem__("pedido", vistos["pedido"] + 1))
    return vistos


def _cancelar(cliente, conta, linha, motivo="Lançado na comanda errada"):
    return cliente.delete(f"/api/v1/orders/{conta.pk}/items/{linha.pk}/void/", {"reason": motivo}, format="json")


def test_cancelamento_na_venda_chega_a_origem_com_motivo_e_autor(api_client, conta_com_comanda, manager_user, avisos):
    conta, linha, anotacao, _comanda = conta_com_comanda

    resposta = _cancelar(api_client, conta, linha)

    assert resposta.status_code == 200, resposta.content
    anotacao.refresh_from_db()
    assert anotacao.status == CommandItem.STATUS_CANCELLED
    assert anotacao.void_reason == "Lançado na comanda errada"
    assert anotacao.voided_by_id == manager_user.pk
    linha.refresh_from_db()
    assert linha.status == OrderItem.STATUS_CANCELLED
    conta.refresh_from_db()
    assert conta.total == Decimal("0.00")


def test_cozinha_recebe_um_aviso_pelo_caminho_da_comanda(api_client, conta_com_comanda, avisos):
    conta, linha, _anotacao, _comanda = conta_com_comanda

    _cancelar(api_client, conta, linha)

    assert avisos == {"comanda": 1, "pedido": 0}


def test_historico_da_comanda_mostra_quem_cancelou_e_por_que(api_client, conta_com_comanda, avisos):
    conta, linha, _anotacao, comanda = conta_com_comanda

    _cancelar(api_client, conta, linha)
    eventos = api_client.get(f"/api/v1/commands/{comanda.pk}/history/").data["results"]

    cancelamento = next(e for e in eventos if e["kind"] == "voided")
    assert cancelamento["reason"] == "Lançado na comanda errada"
    assert cancelamento["user"]


def test_fora_do_prazo_continua_pedindo_autorizacao(api_client, conta_com_comanda, restaurant, avisos):
    """A regra do restaurante vale do mesmo jeito, venha o cancelamento de onde vier."""
    conta, linha, anotacao, _comanda = conta_com_comanda
    restaurant.item_cancel_window_seconds = 60
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    CommandItem.objects.filter(pk=anotacao.pk).update(sent_to_kitchen_at=timezone.now() - timezone.timedelta(minutes=5))
    OrderItem.objects.filter(pk=linha.pk).update(sent_to_kitchen_at=timezone.now() - timezone.timedelta(minutes=5))

    resposta = _cancelar(api_client, conta, linha)

    assert resposta.status_code == 409
    anotacao.refresh_from_db()
    assert anotacao.status != CommandItem.STATUS_CANCELLED
