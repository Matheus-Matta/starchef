"""O pedido aberto na NUVEM chega à loja com o total que a nuvem calculou.

O defeito: com a loja fora, o PDV desvia para a nuvem e abre o pedido de
balcão lá. O pedido nasce vazio (total 0) e só ganha total quando o primeiro
item entra. Os dois eventos descem quando a loja volta: o INSERT é aplicado,
mas a atualização com o total virava CONFLITO — `order` é `LOJA` ("a loja
vence"), e a loja recusava toda versão mais nova da nuvem. O item aparecia na
loja e o pedido ficava com total R$ 0,00. Na nuvem estava certo.

"A loja vence" protege uma edição da loja que a nuvem ainda não viu. Um
pedido que VEIO da nuvem e que a loja nunca editou não tem edição nenhuma
da loja para proteger.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.synchronization.constants import EventStatus
from apps.synchronization.models import SyncConflict, SyncEvent
from apps.synchronization.services import conflicts, crypto
from apps.synchronization.tests.test_comanda_zerada_na_nuvem import (  # noqa: F401 — fixture
    _agora,
    _decidir,
    _Linha,
    _na_loja,
    _subiu,
)

pytestmark = pytest.mark.django_db

_sequencia = iter(range(500, 10_000))


def _desce(conta, no_loja, no_nuvem, entidade, entity_id, campos, versao):
    """Um evento da nuvem pelo caminho real do worker da loja."""
    from apps.synchronization import worker_steps

    payload = {"schema_version": 1, "entity_type": entidade, "entity_id": str(entity_id),
               "entity_version": versao, "origin_node_id": str(no_nuvem.id), "fields": campos}
    bruto = {
        "event_id": str(uuid.uuid4()), "account_id": str(conta.id),
        "target_node_id": str(no_loja.id), "sequence": next(_sequencia),
        "entity_type": entidade, "entity_id": str(entity_id), "operation": "UPSERT",
        "entity_version": versao, "payload": payload,
        "payload_checksum": crypto.checksum(payload),
    }
    ids = worker_steps.registrar_lote_recebido({"events": [bruto]}, str(no_nuvem.id))
    return worker_steps.aplicar_recebidos(ids)


def test_pedido_aberto_na_nuvem_chega_a_loja_com_o_total(conta, no_loja, no_nuvem):
    """O pedido de balcão nasce vazio na nuvem e ganha o total no 1º item."""
    from apps.orders.models import Order
    from apps.restaurants.models import Restaurant
    from apps.synchronization.services import serialization
    from apps.synchronization.services.registry import registry

    restaurante = Restaurant.objects.create(account=conta, legal_name="R LTDA", trade_name="R")
    molde = Order.objects.create(account=conta, restaurant=restaurante, status="open", sequence=413)
    vazio = serialization.serialize(molde, registry.get("order"))
    pedido_id = molde.pk
    # O molde só empresta os campos: o pedido nunca existiu na loja, e o
    # evento de saída que a criação dele gerou também não.
    Order.all_objects.filter(pk=pedido_id).delete()
    SyncEvent.objects.filter(entity_id=str(pedido_id)).delete()
    aberto_em = molde.updated_at - timedelta(minutes=10)

    _desce(conta, no_loja, no_nuvem, "order", pedido_id,
           {**vazio, "updated_at": aberto_em.isoformat()},
           int(aberto_em.timestamp() * 1_000_000))
    com_item = aberto_em + timedelta(seconds=3)
    _desce(conta, no_loja, no_nuvem, "order", pedido_id,
           {**vazio, "subtotal": "5.99", "total": "5.99", "updated_at": com_item.isoformat()},
           int(com_item.timestamp() * 1_000_000))

    pedido = Order.all_objects.get(pk=pedido_id)
    assert pedido.total == Decimal("5.99")
    assert not SyncConflict.objects.filter(entity_id=str(pedido_id)).exists()


def _veio_da_nuvem(conta, no_loja, no_nuvem, entidade, linha, aplicado):
    """A linha chegou da nuvem e foi aplicada aqui em `aplicado`."""
    from apps.synchronization.constants import Direction, Operation
    from apps.synchronization.models import SyncEvent

    payload = {"fields": {}}
    SyncEvent.objects.create(
        account=conta, source_node=no_nuvem, target_node=no_loja,
        direction=Direction.INBOUND, sequence=next(_sequencia), entity_type=entidade,
        entity_id=str(linha.pk), operation=Operation.UPSERT, entity_version=1,
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.APPLIED, applied_at=aplicado,
    )


@pytest.mark.parametrize("entidade", ["order", "order_item", "order_item_addon", "order_batch"])
def test_linha_do_pedido_vinda_da_nuvem_e_editada_por_ela_aplica(
    conta, no_loja, no_nuvem, entidade
):
    linha = _Linha(uuid.uuid4())
    aplicado = timezone.now()
    _veio_da_nuvem(conta, no_loja, no_nuvem, entidade, linha, aplicado)
    local = int(aplicado.timestamp() * 1_000_000) - 1000

    assert _decidir(entidade, linha, local=local, remoto=_agora() + 1) == conflicts.APLICAR


def test_pedido_que_a_loja_editou_antes_perde_para_a_versao_mais_nova(conta, no_loja, no_nuvem):
    """A loja mexeu e isso ainda não subiu, mas a nuvem mexeu DEPOIS: vence a
    da nuvem. Antes virava conflito e o pedido ficava com o total antigo."""
    linha = _Linha(uuid.uuid4())
    _veio_da_nuvem(conta, no_loja, no_nuvem, "order", linha,
                   timezone.now() - timedelta(minutes=1))
    local = _agora() - 1000
    _subiu(conta, no_loja, no_nuvem, "order", linha, versao=local, status=EventStatus.PENDING)

    assert _decidir("order", linha, local=local, remoto=_agora()) == conflicts.APLICAR


def test_pagamento_mais_novo_vindo_da_nuvem_tambem_entra(conta, no_loja, no_nuvem):
    """O pagamento feito na nuvem com a loja fora precisa chegar à loja."""
    linha = _Linha(uuid.uuid4())
    aplicado = timezone.now()
    _veio_da_nuvem(conta, no_loja, no_nuvem, "payment", linha, aplicado)
    local = int(aplicado.timestamp() * 1_000_000) - 1000

    assert _decidir("payment", linha, local=local, remoto=_agora() + 1) == conflicts.APLICAR
