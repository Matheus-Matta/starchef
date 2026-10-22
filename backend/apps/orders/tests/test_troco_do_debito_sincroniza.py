"""Débito com troco em dinheiro: o troco que sai da gaveta precisa sincronizar.

Relato da loja: uma venda no débito com R$ 50 de troco não chegou ao outro
lado. O fechamento (feito onde a venda estava) esperava R$ 83,24; o extrato
(do lado sem a venda) somava R$ 133,24 — exatamente os R$ 50 do troco.
"""
from decimal import Decimal

import pytest

from apps.orders.tests.test_venda_inteira import URL, _venda
from apps.orders.tests.test_venda_inteira_sincroniza_em_lote import nuvem_com_loja  # noqa: F401
from apps.payments.models import CashMovement, PaymentMethod
from apps.payments.services import open_cash_register
from apps.synchronization.models import SyncEvent

pytestmark = pytest.mark.django_db


def _venda_no_debito_com_troco(api_client, restaurant, branch, account, produto, manager_user):
    """Pedido de R$ 50, débito de R$ 100: R$ 50 de troco saem da gaveta."""
    cartao = PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch,
                                          name="Cartão", method_type=PaymentMethod.TYPE_CARD)
    caixa = open_cash_register(restaurant=restaurant, user=manager_user, opening_amount=Decimal("100.00"))
    corpo = _venda(restaurant, produto, cartao, itens=2, valor="100.00")
    corpo["payments"][0]["metadata"] = {"card_subtype": "debit"}
    resposta = api_client.post(URL, corpo, format="json")
    assert resposta.status_code == 201, resposta.content
    return caixa, corpo


def test_venda_no_debito_com_troco_gera_evento_do_pedido_do_recebimento_e_do_troco(
    api_client, contexto_tenant, restaurant, branch, account, produto, manager_user,
    nuvem_com_loja,  # noqa: F811
):
    caixa, corpo = _venda_no_debito_com_troco(api_client, restaurant, branch, account, produto, manager_user)

    troco = CashMovement.all_objects.get(cash_register=caixa, movement_type=CashMovement.TYPE_WITHDRAWAL)
    assert troco.amount == Decimal("-50.00")
    eventos = set(SyncEvent.objects.values_list("entity_type", "entity_id"))
    assert ("order", corpo["id"]) in eventos
    assert ("payment", corpo["payments"][0]["id"]) in eventos
    assert ("cash_movement", str(troco.pk)) in eventos


def _como_a_loja_mandaria(instancias, origem):
    from apps.synchronization.services import serialization
    from apps.synchronization.services.registry import registry

    return [serialization.build_payload(i, registry.for_model(type(i)), origin_node_id=origem.id)
            for i in instancias]


def _aplicar_no_destino(payloads, origem, destino, rodadas=5):
    """Aplica como o outro servidor: o que espera o pai entra na rodada seguinte."""
    from apps.synchronization.constants import Direction, EventStatus, Operation
    from apps.synchronization.services import apply, crypto

    eventos = [SyncEvent.objects.create(
        account=destino.account, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=900 + n,
        entity_type=p["entity_type"], entity_id=p["entity_id"], operation=Operation.UPSERT,
        entity_version=p["entity_version"], payload=p, payload_checksum=crypto.checksum(p),
        status=EventStatus.RECEIVED,
    ) for n, p in enumerate(payloads)]
    for _ in range(rodadas):
        for evento in eventos:
            evento.refresh_from_db()
            apply.apply_event(evento)
    presos = []
    for evento in eventos:
        evento.refresh_from_db()
        if evento.status != EventStatus.APPLIED or evento.last_error:
            presos.append((evento.entity_type, evento.status, evento.last_error[:160]))
    return presos


def test_troco_do_debito_chega_no_outro_servidor_mesmo_fora_de_ordem(
    api_client, contexto_tenant, restaurant, branch, account, produto, manager_user,
    nuvem_com_loja,  # noqa: F811
):
    from apps.orders.models import Order, OrderItem
    from apps.payments.models import Payment
    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode

    caixa, corpo = _venda_no_debito_com_troco(api_client, restaurant, branch, account, produto, manager_user)
    pedido = Order.all_objects.get(pk=corpo["id"])
    itens = list(OrderItem.all_objects.filter(order=pedido))
    pagamento = Payment.all_objects.get(order=pedido)
    troco = CashMovement.all_objects.get(payment=pagamento)
    loja = SyncNode.objects.get(node_type=NodeType.LOCAL)
    nuvem = SyncNode.objects.get(node_type=NodeType.CLOUD)
    # O PIOR caminho: o troco chega antes do recebimento, que chega antes do pedido.
    payloads = _como_a_loja_mandaria([troco, pagamento, *itens, pedido], loja)

    # O "outro servidor": a venda nunca esteve aqui. O caixa, sim.
    CashMovement.all_objects.filter(pk=troco.pk).delete()
    Payment.all_objects.filter(pk=pagamento.pk).delete()
    OrderItem.all_objects.filter(order=pedido).delete()
    Order.all_objects.filter(pk=pedido.pk).delete()
    SyncEvent.objects.all().delete()

    presos = _aplicar_no_destino(payloads, loja, nuvem)

    assert presos == []
    assert Payment.all_objects.filter(pk=pagamento.pk).exists()
    chegou = CashMovement.all_objects.get(pk=troco.pk)
    assert chegou.amount == Decimal("-50.00") and chegou.status == "approved"
    assert chegou.cash_register_id == caixa.pk
