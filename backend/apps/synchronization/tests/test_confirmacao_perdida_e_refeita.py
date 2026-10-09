"""A confirmação ("apliquei") que se perdeu na rede é refeita.

O destino aplica, manda o ACK e marca o evento como confirmado. Se o ACK cai
junto com a rede, a origem fica com o evento em RECEIVED para sempre: ela não
reenvia (só reenviava SENT) e o destino não confirma de novo (já marcou). No par
real (`loadtest/dia_a_dia`), 172 eventos presos assim depois das quedas.

Agora a origem reenvia o RECEIVED antigo, e o destino, ao receber de novo um
evento que já aplicou, volta a confirmá-lo.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import crypto, inbox

pytestmark = pytest.mark.django_db


def _evento(conta, origem, destino, direcao, status, sequencia=1):
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino, direction=direcao,
        sequence=sequencia, entity_type="command", entity_id="c1", operation=Operation.UPSERT,
        entity_version=1, payload={}, payload_checksum=crypto.checksum({}), status=status,
    )


def test_evento_ja_confirmado_que_chega_de_novo_volta_a_ser_confirmado(
    como_nuvem, conta, no_nuvem, no_loja
):
    ja_aplicado = _evento(conta, no_loja, no_nuvem, Direction.INBOUND, EventStatus.ACKNOWLEDGED)

    inbox.store_batch([{
        "event_id": str(ja_aplicado.event_id), "account_id": str(conta.id),
        "target_node_id": str(no_nuvem.id), "sequence": 1, "entity_type": "command",
        "entity_id": "c1", "operation": "UPSERT", "entity_version": 1, "payload": {},
        "payload_checksum": crypto.checksum({}),
    }], connection_node=no_loja, account_id=conta.id)

    ja_aplicado.refresh_from_db()
    assert ja_aplicado.status == EventStatus.APPLIED  # na fila de confirmação


def test_received_antigo_volta_para_a_fila_da_origem(como_loja, conta, no_nuvem, no_loja):
    from apps.synchronization.tasks.reconcile import reconcile_nodes

    preso = _evento(conta, no_loja, no_nuvem, Direction.OUTBOUND, EventStatus.RECEIVED)
    SyncEvent.objects.filter(pk=preso.pk).update(sent_at=timezone.now() - timedelta(minutes=10))

    reconcile_nodes()

    preso.refresh_from_db()
    assert preso.status == EventStatus.PENDING
