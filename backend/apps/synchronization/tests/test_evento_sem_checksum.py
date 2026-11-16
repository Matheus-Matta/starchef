"""Evento sem checksum não entra: vai para a quarentena, e o lote segue."""
import pytest

from apps.synchronization.services import inbox
from apps.synchronization.tests.test_lote_isola_evento_ruim import _evento

pytestmark = pytest.mark.django_db


def test_evento_sem_checksum_vai_para_a_quarentena(como_nuvem, conta, no_loja, no_nuvem):
    """Sem checksum o evento era gravado com um checksum calculado na chegada,
    que conferia sempre — truncado ou adulterado passava como íntegro."""
    sem = _evento(conta, no_nuvem)
    del sem["payload_checksum"]
    bom = _evento(conta, no_nuvem, sequence=2)

    aceitos, _maior, recusados = inbox.store_batch([sem, bom], connection_node=no_loja, account_id=conta.id)

    assert [str(e.event_id) for e in aceitos] == [bom["event_id"]]
    assert recusados and "sem checksum" in recusados[0]["error"]
