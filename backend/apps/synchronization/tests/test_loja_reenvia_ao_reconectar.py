"""Ao reconectar, a loja reenvia NA HORA o que saiu e não foi confirmado.

Um lote transmitido no instante em que a rede caiu fica SENT: saiu do socket e
nunca chegou. A nuvem reenfileira o dela no aperto de mão; a loja não — ela
dependia de `reconcile_nodes`, que só pega o que está SENT há mais de 5
minutos. No par real (`loadtest/dia_a_dia`), depois de cada queda os itens
da comanda esperavam o lote de cozinha que estava parado em SENT, e a nuvem
passava esses minutos sem eles.
"""
import pytest

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent

pytestmark = pytest.mark.django_db


def test_reconectar_devolve_o_sent_para_a_fila(como_loja, conta, no_nuvem, no_loja):
    from apps.synchronization.worker_steps import ao_reconectar

    perdido = SyncEvent.objects.create(
        account=conta, source_node=no_loja, target_node=no_nuvem, direction=Direction.OUTBOUND,
        sequence=900, entity_type="command_batch", entity_id="x", operation=Operation.UPSERT,
        entity_version=1, payload={}, payload_checksum="x", status=EventStatus.SENT,
    )

    ao_reconectar()

    perdido.refresh_from_db()
    assert perdido.status == EventStatus.PENDING
