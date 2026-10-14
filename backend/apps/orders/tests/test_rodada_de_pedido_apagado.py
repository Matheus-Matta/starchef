"""Rodada agendada de um pedido apagado não derruba a fila de impressão.

Achado no docker da loja: `GET /print-jobs/` respondia 500 em TODA chamada.
A lista libera as rodadas vencidas antes de responder, e uma delas era de um
pedido já apagado (pedido vazio descartado). A rodada sem item para a cozinha
recalcula o status do pedido com `Order.objects` — que não enxerga apagado —
e o `DoesNotExist` subia. Os PDVs não recebiam mais nenhum trabalho de
impressão: nem recibo, nem cozinha, nem etiqueta.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import Order, OrderBatch, OrderItem
from apps.orders.services import create_order, dispatch_due_kitchen_batches

pytestmark = pytest.mark.django_db


def _rodada_vencida(pedido, usuario):
    agora = timezone.now() - timedelta(minutes=1)
    return OrderBatch.objects.create(
        account=pedido.account, restaurant=pedido.restaurant, branch=pedido.branch, order=pedido,
        batch_number=1, status=OrderBatch.STATUS_SCHEDULED, sent_at=agora,
        dispatch_at=agora + timedelta(seconds=10), sent_by=usuario,
        created_by=usuario, updated_by=usuario,
    )


@pytest.fixture
def pedido_apagado(contexto_tenant, restaurant, branch, manager_user):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    rodada = _rodada_vencida(pedido, manager_user)
    Order.all_objects.filter(pk=pedido.pk).update(deleted_at=timezone.now())
    return pedido, rodada


def test_liberar_rodada_de_pedido_apagado_nao_quebra(pedido_apagado):
    _, rodada = pedido_apagado

    dispatch_due_kitchen_batches()

    # Sai da fila (o pedido não existe mais, então ela é cancelada) — e nada quebra.
    rodada.refresh_from_db()
    assert rodada.status != OrderBatch.STATUS_SCHEDULED


def test_uma_rodada_quebrada_nao_impede_as_outras(pedido_apagado, monkeypatch, restaurant, branch,
                                                   manager_user, produto):
    """Qualquer falha numa rodada fica nela: as outras saem, e quem chamou não cai."""
    from apps.orders import services
    from apps.orders.services import add_order_item

    boa_pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                              user=manager_user)
    add_order_item(order=boa_pedido, product=produto, quantity=1, user=manager_user)
    boa = _rodada_vencida(boa_pedido, manager_user)
    OrderItem.all_objects.filter(order=boa_pedido).update(batch=boa, status=OrderItem.STATUS_QUEUED)
    _, ruim = pedido_apagado
    original = services.dispatch_kitchen_batch

    def quebrar_a_ruim(batch, **kwargs):
        if batch.pk == ruim.pk:
            raise RuntimeError("defeito qualquer")
        return original(batch, **kwargs)

    monkeypatch.setattr(services, "dispatch_kitchen_batch", quebrar_a_ruim)

    dispatch_due_kitchen_batches()

    boa.refresh_from_db()
    assert boa.status == OrderBatch.STATUS_SENT


def test_a_fila_de_impressao_responde_mesmo_com_a_rodada_quebrada(pedido_apagado, api_client,
                                                                   restaurant):
    resposta = api_client.get("/api/v1/print-jobs/", {
        "restaurant": str(restaurant.pk), "status__in": "scheduled,pending,rendered"})

    assert resposta.status_code == 200
