"""A rematrícula quando o OUTRO LADO trocou de id.

É o caso para o qual a rematrícula existe, e era o único em que ela não
funcionava.

A unicidade de `SyncNode` é `(pair_id, node_type)`, e a gravação buscava por
`pk`. Com um id novo, ela não encontrava nada, tentava inserir e batia na
chave única do registro velho — `IntegrityError` no meio da instalação, DEPOIS
de a nuvem já ter consumido o bilhete. O comando falhava e o bilhete morria, a
cada tentativa.

Aconteceu de verdade: uma migração de limpeza na nuvem fundiu nós `is_self`
duplicados e apagou aquele que uma loja tinha guardado na matrícula. A loja
passou a endereçar todo evento para um nó inexistente — que os recusava um a
um — e não conseguia se rematricular para sair disso.
"""
import uuid

import pytest

from apps.synchronization.constants import Direction, EventStatus, NodeType
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import enrollment_client

pytestmark = pytest.mark.django_db


def _pacote(conta, no_loja, peer_id):
    return {
        "SYNC_ACCOUNT_ID": str(conta.id),
        "SYNC_NODE_ID": str(no_loja.id),
        "SYNC_PAIR_ID": str(no_loja.pair_id),
        "SYNC_PEER_NODE_ID": str(peer_id),
        "SYNC_NODE_NAME": "Servidor da loja",
    }


def test_a_rematricula_ACEITA_um_id_novo_para_a_nuvem(como_loja, conta, no_loja, no_nuvem):
    """O defeito. Antes, isto estourava com IntegrityError."""
    novo_id = uuid.uuid4()

    proprio = enrollment_client.install(_pacote(conta, no_loja, novo_id))

    assert str(proprio.peer_id) == str(novo_id)
    assert SyncNode.objects.filter(pk=novo_id, node_type=NodeType.CLOUD).exists()


def test_o_no_antigo_SOME_e_nao_bloqueia_a_chave_unica(
    como_loja, conta, no_loja, no_nuvem
):
    """Dois nós da nuvem no mesmo par seriam a própria ambiguidade de endereço
    que este conserto existe para acabar."""
    antigo = no_nuvem.id
    novo_id = uuid.uuid4()

    enrollment_client.install(_pacote(conta, no_loja, novo_id))

    assert not SyncNode.objects.filter(pk=antigo).exists()
    assert SyncNode.objects.filter(
        pair_id=no_loja.pair_id, node_type=NodeType.CLOUD
    ).count() == 1


def test_o_HISTORICO_acompanha_a_identidade_nova(como_loja, conta, no_loja, no_nuvem):
    """Nada de histórico se perde: é a mesma instalação, com outro nome.

    Os eventos que a loja já trocou com a nuvem continuam existindo e passam a
    apontar para o id novo — senão as chaves estrangeiras (`PROTECT`) nem
    deixariam o registro velho sair.
    """
    evento = SyncEvent.objects.create(
        event_id=uuid.uuid4(),
        account=conta,
        source_node=no_nuvem,
        target_node=no_loja,
        direction=Direction.INBOUND,
        sequence=1,
        entity_type="restaurant",
        entity_id=str(uuid.uuid4()),
        operation="UPSERT",
        payload={},
        status=EventStatus.APPLIED,
    )
    novo_id = uuid.uuid4()

    enrollment_client.install(_pacote(conta, no_loja, novo_id))

    evento.refresh_from_db()
    assert str(evento.source_node_id) == str(novo_id)


def test_rematricula_com_o_MESMO_id_nao_mexe_em_nada(como_loja, conta, no_loja, no_nuvem):
    """O caminho normal, que não pode pagar o preço do excepcional."""
    enrollment_client.install(_pacote(conta, no_loja, no_nuvem.id))

    assert SyncNode.objects.filter(pk=no_nuvem.id).exists()
    assert SyncNode.objects.filter(
        pair_id=no_loja.pair_id, node_type=NodeType.CLOUD
    ).count() == 1
