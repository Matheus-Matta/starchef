"""A chave de idempotência precisa chegar ao outro nó.

O catálogo declara `idempotency_record` com `flow="bidirectional"` — um valor
que nenhum portão reconhece (`registry.flows_to_*` só conhecem `both`,
`cloud_to_local` e `local_to_cloud`). A outbox recusava o evento na origem,
nos dois sentidos, e a proteção que o comentário do catálogo descreve nunca
existiu: a loja volta, a fila do terminal reenvia a venda que a NUVEM já
gravou, e a loja não reconhece a chave — segunda venda.
"""
import pytest

from apps.synchronization.constants import Direction
from apps.synchronization.models import SyncEvent
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


def test_a_chave_de_idempotencia_sobe_e_desce():
    assert registry.flows_to_cloud("idempotency_record")
    assert registry.flows_to_local("idempotency_record")


def test_toda_entrada_do_catalogo_tem_uma_direcao_que_os_portoes_conhecem():
    """Um valor de `flow` digitado errado desliga a entidade sem erro nenhum."""
    conhecidas = {"both", "cloud_to_local", "local_to_cloud"}
    for entrada in registry.ordered():
        assert entrada.flow in conhecidas, entrada.entity_type


def test_a_chave_gravada_na_loja_vira_evento_para_a_nuvem(como_loja, conta, no_nuvem):
    from apps.core.models import IdempotencyRecord

    registro = IdempotencyRecord.objects.create(
        account=conta, key="op-1", method="POST", path="/api/v1/orders/",
        request_fingerprint="f" * 64, status_code=201, response_body={"id": "x"},
    )

    assert SyncEvent.objects.filter(
        direction=Direction.OUTBOUND, entity_type="idempotency_record",
        entity_id=str(registro.pk),
    ).exists()
