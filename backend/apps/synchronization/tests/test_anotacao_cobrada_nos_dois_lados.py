"""A mesma anotação de comanda cobrada na loja E na nuvem não trava a fila.

No restaurante todo mundo usa a loja ou todo mundo usa a nuvem; os dois só
recebem ao mesmo tempo na TROCA (a loja cai, volta). Nessa janela um caixa
fechou a comanda 523 na loja e outro, já na nuvem, fechou a mesma comanda antes
de a cobrança da loja chegar lá (`loadtest/dia_a_dia`: 202 anotações em dois
pedidos). O caixa decide — nada é bloqueado —, mas a chegada do item da outra
ponta batia em `unique_order_item_per_command_item`: conflito, o item nunca
entrava, e o estoque dele ficava retentando para sempre (648 eventos parados).

A regra é a mesma nos dois lados, para terminarem iguais sem conversar: o item
MAIS NOVO (`updated_at`) fica com a anotação; o mais velho entra assim mesmo —
o pedido e o pagamento dele existem —, só que sem o vínculo.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_item_launch import launch_item
from apps.orders.models import Order, OrderItem
from apps.orders.services import create_order
from apps.restaurants.models import Command
from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncConflict, SyncEvent
from apps.synchronization.services import apply, crypto, serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


@pytest.fixture
def cobrada_na_loja(como_loja, account, restaurant, branch, manager_user):
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Brownie", internal_code="SYNC-BROWNIE",
                                     sale_price=Decimal("48.00"))
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     number=523)
    with tenant_context(account):
        anotacao = launch_item(command=comanda, product=produto, user=manager_user)
    pedido_da_loja = create_order(restaurant=restaurant, branch=branch,
                                  order_type=Order.TYPE_COUNTER, user=manager_user)
    [item_da_loja] = attach_commands_to_order(order=pedido_da_loja, command_ids=[comanda.pk],
                                              user=manager_user)
    # O pedido da nuvem já desceu (é dependência do item); o item dele chega agora.
    pedido_da_nuvem = create_order(restaurant=restaurant, branch=branch,
                                   order_type=Order.TYPE_COUNTER, user=manager_user)
    return item_da_loja, pedido_da_nuvem, anotacao


def _item_chega_da_nuvem(conta, no_nuvem, no_loja, item_da_loja, pedido, quando):
    remoto = OrderItem.all_objects.get(pk=item_da_loja.pk)
    remoto.pk, remoto.order = uuid.uuid4(), pedido
    remoto.created_at = remoto.updated_at = quando
    payload = serialization.build_payload(remoto, registry.require("order_item"),
                                          origin_node_id=no_nuvem.id)
    evento = SyncEvent.objects.create(
        account=conta, source_node=no_nuvem, target_node=no_loja, direction=Direction.INBOUND,
        sequence=901, entity_type="order_item", entity_id=str(remoto.pk),
        operation=Operation.UPSERT, entity_version=payload["entity_version"], payload=payload,
        payload_checksum=crypto.checksum(payload), status=EventStatus.RECEIVED,
    )
    apply.apply_event(evento)
    evento.refresh_from_db()
    return remoto.pk, evento


def test_cobranca_mais_nova_da_nuvem_fica_com_a_anotacao(conta, no_nuvem, no_loja, cobrada_na_loja):
    item_da_loja, pedido_da_nuvem, anotacao = cobrada_na_loja
    remoto, evento = _item_chega_da_nuvem(conta, no_nuvem, no_loja, item_da_loja, pedido_da_nuvem,
                                          timezone.now() + timedelta(minutes=1))

    assert evento.status == EventStatus.APPLIED
    assert OrderItem.all_objects.get(pk=remoto).command_item_id == anotacao.pk
    assert OrderItem.all_objects.get(pk=item_da_loja.pk).command_item_id is None
    assert not SyncConflict.objects.filter(entity_type="order_item").exists()
    # O item da loja perdeu o vínculo AQUI: a mudança viaja, senão a nuvem não converge.
    assert SyncEvent.objects.filter(direction=Direction.OUTBOUND, entity_type="order_item",
                                    entity_id=str(item_da_loja.pk),
                                    payload__fields__command_item_id=None).exists()


def test_cobranca_mais_velha_da_nuvem_entra_sem_a_anotacao(conta, no_nuvem, no_loja, cobrada_na_loja):
    item_da_loja, pedido_da_nuvem, anotacao = cobrada_na_loja
    remoto, evento = _item_chega_da_nuvem(conta, no_nuvem, no_loja, item_da_loja, pedido_da_nuvem,
                                          timezone.now() - timedelta(minutes=1))

    assert evento.status == EventStatus.APPLIED
    assert OrderItem.all_objects.get(pk=item_da_loja.pk).command_item_id == anotacao.pk
    # Entra mesmo sem o vínculo: o pedido da nuvem foi pago com ele.
    assert OrderItem.all_objects.get(pk=remoto).command_item_id is None
    assert not SyncConflict.objects.filter(entity_type="order_item").exists()


def test_atualizacao_que_traz_a_anotacao_de_volta_tambem_resolve(
    conta, no_nuvem, no_loja, cobrada_na_loja
):
    """O item da nuvem entrou aqui sem o vínculo (era o mais velho). Depois, lá,
    ele muda (a cozinha marca pronto) ANTES de a nuvem saber da cobrança da
    loja — e a atualização chega com o vínculo de volta, mais nova que o item
    daqui: batia na trava única e ficava retentando para sempre."""
    item_da_loja, pedido_da_nuvem, anotacao = cobrada_na_loja
    remoto, _ = _item_chega_da_nuvem(conta, no_nuvem, no_loja, item_da_loja, pedido_da_nuvem,
                                     timezone.now() - timedelta(minutes=1))
    atualizado = OrderItem.all_objects.get(pk=remoto)
    atualizado.command_item_id, atualizado.status = anotacao.pk, "ready"
    atualizado.updated_at = timezone.now() + timedelta(minutes=1)
    payload = serialization.build_payload(atualizado, registry.require("order_item"),
                                          origin_node_id=no_nuvem.id)
    evento = SyncEvent.objects.create(
        account=conta, source_node=no_nuvem, target_node=no_loja, direction=Direction.INBOUND,
        sequence=902, entity_type="order_item", entity_id=str(remoto),
        operation=Operation.UPSERT, entity_version=payload["entity_version"], payload=payload,
        payload_checksum=crypto.checksum(payload), status=EventStatus.RECEIVED,
    )
    apply.apply_event(evento)
    evento.refresh_from_db()

    assert evento.status == EventStatus.APPLIED, evento.last_error
    assert OrderItem.all_objects.get(pk=remoto).command_item_id == anotacao.pk
    assert OrderItem.all_objects.get(pk=item_da_loja.pk).command_item_id is None
