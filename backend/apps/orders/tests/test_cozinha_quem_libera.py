"""Só quem tem a cozinha libera a rodada — e rodada imediata nunca é liberada de novo.

Achado no par Docker (`loadtest/dia_a_dia`): a loja criou e liberou a rodada na
hora; ela chegou à nuvem ainda "agendada" (o "liberada" vinha atrás), e a
tarefa periódica da nuvem a liberou DE NOVO. Ao salvar o pedido, a nuvem gerou
uma versão nova dele — de antes de o pagamento chegar lá, "aberto" — e a loja,
vendo uma versão mais nova, desfez o pagamento. Impressora e KDS ficam na loja:
com servidor de loja, quem libera é ela. E rodada imediata já sai liberada na
criação: "agendada" nela é só a sincronização atrasada.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import Order, OrderBatch, OrderItem
from apps.orders.services import add_order_item, create_order, dispatch_due_kitchen_batches
from apps.orders.tests.test_comanda_fecha_em_qualquer_servidor import nuvem_com_loja  # noqa: F401

pytestmark = pytest.mark.django_db


def _rodada(pedido, usuario, *, carencia):
    agora = timezone.now() - timedelta(minutes=1)
    rodada = OrderBatch.objects.create(
        account=pedido.account, restaurant=pedido.restaurant, branch=pedido.branch, order=pedido,
        batch_number=1, status=OrderBatch.STATUS_SCHEDULED, sent_at=agora,
        dispatch_at=agora + timedelta(seconds=carencia), sent_by=usuario,
        created_by=usuario, updated_by=usuario,
    )
    OrderItem.all_objects.filter(order=pedido).update(batch=rodada, status=OrderItem.STATUS_QUEUED)
    return rodada


@pytest.fixture
def pedido(contexto_tenant, restaurant, branch, produto, manager_user):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    return pedido


def test_rodada_imediata_agendada_e_sincronizacao_atrasada_nao_se_libera(pedido, manager_user):
    rodada = _rodada(pedido, manager_user, carencia=0)

    dispatch_due_kitchen_batches()

    rodada.refresh_from_db()
    assert rodada.status == OrderBatch.STATUS_SCHEDULED


def test_na_nuvem_com_loja_a_rodada_com_carencia_e_da_loja(nuvem_com_loja, pedido, manager_user):  # noqa: F811
    rodada = _rodada(pedido, manager_user, carencia=10)

    dispatch_due_kitchen_batches()

    rodada.refresh_from_db()
    assert rodada.status == OrderBatch.STATUS_SCHEDULED


def test_sem_loja_a_rodada_com_carencia_e_liberada(pedido, manager_user):
    rodada = _rodada(pedido, manager_user, carencia=10)

    dispatch_due_kitchen_batches()

    rodada.refresh_from_db()
    assert rodada.status == OrderBatch.STATUS_SENT
