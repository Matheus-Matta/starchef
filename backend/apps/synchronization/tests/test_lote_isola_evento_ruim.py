"""Um evento estragado não pode levar o lote junto.

O lote inteiro vinha numa transação só, e qualquer evento inválido derrubava
todos: nada era gravado, a origem não recebia confirmação, reenviava o MESMO
lote e batia no mesmo evento. Para sempre — e tudo que vinha atrás dele nunca
chegava.

O que NÃO mudou: nada estragado é gravado, e tudo fica no log. O que mudou é
quem paga a conta — o evento, não a fila inteira.
"""
import uuid

import pytest

from apps.synchronization.constants import PROTOCOL_VERSION, EventStatus
from apps.synchronization.services import crypto, inbox

pytestmark = pytest.mark.django_db


def _hello(no, **extra):
    base = {
        "node_id": str(no.id),
        "pair_id": str(no.pair_id),
        "account_id": str(no.account_id),
        "environment": no.environment,
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": 1,
        "app_version": "3.0.0",
    }
    base.update(extra)
    return base


def _evento(conta, destino, **extra):
    bruto = {
        "event_id": str(uuid.uuid4()),
        "account_id": str(conta.id),
        "target_node_id": str(destino.id),
        "sequence": 1,
        "entity_type": "restaurant",
        "entity_id": str(uuid.uuid4()),
        "operation": "UPSERT",
        "payload": {"fields": {}},
    }
    bruto.update(extra)
    return bruto


def test_evento_para_outro_destino_nao_e_gravado(como_nuvem, conta, no_loja, no_nuvem):
    """Endereçado a outro nó: vai para a quarentena, não para a inbox."""
    from apps.synchronization.models import SyncEvent

    bruto = _evento(conta, no_nuvem, target_node_id=str(uuid.uuid4()))

    aceitos, _maior, recusados = inbox.store_batch(
        [bruto], connection_node=no_loja, account_id=conta.id
    )

    assert aceitos == []
    assert len(recusados) == 1
    assert recusados[0]["event_id"] == bruto["event_id"]

    # FICA gravado, como DEAD e com o motivo. Antes era descartado com uma
    # linha de log, e foi isso que escondeu por um dia inteiro uma loja
    # endereçando tudo para um nó apagado: 729 eventos, pagamentos incluídos,
    # foram para o ralo com a fila dizendo "0 mortos".
    guardado = SyncEvent.objects.get(event_id=bruto["event_id"])
    assert guardado.status == EventStatus.DEAD
    assert "target_node" in guardado.last_error


def test_um_evento_estragado_nao_derruba_os_outros(como_nuvem, conta, no_loja, no_nuvem):
    """O defeito que isto existe para impedir: bloqueio de cabeça de fila.

    O lote inteiro vinha numa transação só. Um evento endereçado a um nó que
    não existe mais derrubava todos, a origem não recebia confirmação,
    reenviava o MESMO lote e batia no mesmo evento — para sempre. Tudo que
    vinha atrás dele nunca chegava.
    """
    from apps.synchronization.models import SyncEvent

    bom_antes = _evento(conta, no_nuvem, sequence=1)
    estragado = _evento(conta, no_nuvem, sequence=2, target_node_id=str(uuid.uuid4()))
    bom_depois = _evento(conta, no_nuvem, sequence=3)

    aceitos, maior, recusados = inbox.store_batch(
        [bom_antes, estragado, bom_depois],
        connection_node=no_loja,
        account_id=conta.id,
    )

    assert len(aceitos) == 2, "o evento ruim levou os bons junto"
    assert estragado["event_id"] not in [str(e.event_id) for e in aceitos]
    assert len(recusados) == 1
    assert SyncEvent.objects.filter(event_id=bom_depois["event_id"]).exists(), (
        "o que vinha DEPOIS do evento ruim precisa chegar"
    )
    assert maior == 3, "o cursor precisa passar do evento recusado"


def test_evento_grande_demais_nao_derruba_o_lote(
    como_nuvem, conta, no_loja, no_nuvem, settings
):
    """O teto de bytes é por evento; a recusa também."""
    settings.SYNC_BATCH_MAX_BYTES = 200

    gigante = _evento(conta, no_nuvem, sequence=1)
    gigante["payload"] = {"fields": {"trade_name": "x" * 5000}}
    pequeno = _evento(conta, no_nuvem, sequence=2)

    aceitos, _maior, recusados = inbox.store_batch(
        [gigante, pequeno], connection_node=no_loja, account_id=conta.id
    )

    assert len(aceitos) == 1
    assert len(recusados) == 1


def test_checksum_divergente_no_evento_e_rejeitado(como_nuvem, conta, no_loja, no_nuvem):
    bruto = {
        "event_id": str(uuid.uuid4()),
        "account_id": str(conta.id),
        "target_node_id": str(no_nuvem.id),
        "sequence": 1,
        "entity_type": "restaurant",
        "entity_id": str(uuid.uuid4()),
        "operation": "UPSERT",
        "payload": {"fields": {"trade_name": "X"}},
        "payload_checksum": crypto.checksum({"outra": "coisa"}),
    }
    # Determinístico: a origem calcula do mesmo payload, então reenviar dá o
    # mesmo resultado. Quarentena, não retentativa eterna.
    from apps.synchronization.models import SyncEvent

    aceitos, _maior, recusados = inbox.store_batch(
        [bruto], connection_node=no_loja, account_id=conta.id
    )

    assert aceitos == []
    assert "Checksum" in recusados[0]["error"]

    # Guardado como DEAD, com o motivo — nunca aplicado, mas nunca invisível.
    guardado = SyncEvent.objects.get(event_id=bruto["event_id"])
    assert guardado.status == EventStatus.DEAD
    assert "Checksum" in guardado.last_error


def test_o_evento_em_quarentena_APARECE_na_fila(como_nuvem, conta, no_loja, no_nuvem):
    """O defeito que custou um dia inteiro de diagnóstico.

    Uma loja endereçava tudo para um nó que a nuvem havia apagado. Os eventos
    eram descartados com uma linha de log, e a fila seguia dizendo "0 mortos"
    — então o painel parecia saudável, o `sync_status` parecia saudável, e 729
    eventos (pagamentos incluídos) simplesmente não chegavam.

    "Mortos" é o número que alguém olha. Se a quarentena não entra nele, ela
    troca um problema barulhento por um invisível.
    """
    from apps.synchronization.models import SyncEvent

    bruto = _evento(conta, no_nuvem, target_node_id=str(uuid.uuid4()))
    inbox.store_batch([bruto], connection_node=no_loja, account_id=conta.id)

    guardado = SyncEvent.objects.get(event_id=bruto["event_id"])
    assert guardado.status == EventStatus.DEAD
    assert SyncEvent.objects.filter(status=EventStatus.DEAD).count() >= 1, (
        "a quarentena não aparece em lugar nenhum"
    )


def test_o_evento_em_quarentena_NUNCA_e_aplicado(como_nuvem, conta, no_loja, no_nuvem):
    """A garantia de segurança que não pode cair junto com a visibilidade.

    Guardar o evento é para ele ser VISTO, não para ser aplicado. `DEAD` fica
    fora de `pending_inbound`, que só olha RECEIVED e FAILED — então nenhuma
    passada do worker o pega.
    """
    from apps.synchronization.models import SyncEvent
    from apps.synchronization.services import nodes as servico_nos

    bruto = _evento(conta, no_nuvem, target_node_id=str(uuid.uuid4()))
    inbox.store_batch([bruto], connection_node=no_loja, account_id=conta.id)

    proprio = servico_nos.self_node()
    pendentes = SyncEvent.objects.pending_inbound(proprio).values_list("event_id", flat=True)

    assert bruto["event_id"] not in [str(e) for e in pendentes]
