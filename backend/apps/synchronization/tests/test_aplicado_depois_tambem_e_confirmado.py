"""O evento aplicado DEPOIS também é confirmado à origem.

O "apliquei" (ACK `acknowledged`) só saía para o que era aplicado na hora em
que o lote chegava. O que esperou o pai e entrou numa retentativa — do beat ou
acordado por `retry.acordar_quem_espera_dependencia` — nunca era confirmado: na
origem ele ficava RECEIVED para sempre. O painel mostrava fila que não zerava e
a limpeza nunca o apagava. No par real (`loadtest/dia_a_dia`) eram 72 presos na
nuvem e 5 na loja.
"""
import pytest

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import confirmacao

pytestmark = pytest.mark.django_db


def _entrada(conta, origem, destino, sequencia, status):
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino, direction=Direction.INBOUND,
        sequence=sequencia, entity_type="command", entity_id=str(sequencia),
        operation=Operation.UPSERT, entity_version=1, payload={}, payload_checksum="x",
        status=status,
    )


def test_aplicado_sem_confirmacao_e_listado_e_depois_marcado(como_loja, conta, no_nuvem, no_loja):
    aplicado = _entrada(conta, no_nuvem, no_loja, 1, EventStatus.APPLIED)
    _entrada(conta, no_nuvem, no_loja, 2, EventStatus.FAILED)
    _entrada(conta, no_nuvem, no_loja, 3, EventStatus.ACKNOWLEDGED)

    pendentes = confirmacao.aplicados_sem_confirmacao(no_nuvem)
    assert pendentes == [str(aplicado.event_id)]

    confirmacao.marcar_confirmados(no_nuvem, pendentes)

    assert confirmacao.aplicados_sem_confirmacao(no_nuvem) == []
    aplicado.refresh_from_db()
    assert aplicado.status == EventStatus.ACKNOWLEDGED


def test_o_que_veio_de_outro_no_nao_entra(como_loja, conta, no_nuvem, no_loja):
    _entrada(conta, no_loja, no_nuvem, 7, EventStatus.APPLIED)

    assert confirmacao.aplicados_sem_confirmacao(no_nuvem) == []
