"""Os três buracos que a revisão de arquitetura apontou e que eram reais.

Cada teste aqui falha na versão anterior do código. Não são testes de
"continua funcionando": são a prova de que o defeito existia.
"""
import uuid

import pytest
from django.utils import timezone

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import (
    ENVIRONMENT_DEVELOPMENT,
    Direction,
    EventStatus,
    NodeStatus,
    NodeType,
    Operation,
)
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import apply, crypto, dispatch, inbox, recovery

pytestmark = pytest.mark.django_db


def _evento_de_entrada(conta, origem, destino, *, entity_id, fields, sequence=1,
                       status=EventStatus.RECEIVED, operation=Operation.UPSERT):
    payload = {
        "schema_version": 1,
        "entity_type": "restaurant",
        "entity_id": str(entity_id),
        "entity_version": 10,
        "origin_node_id": str(origem.id),
        "fields": fields,
    }
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=sequence, entity_type="restaurant",
        entity_id=str(entity_id), operation=operation, entity_version=10,
        payload=payload, payload_checksum=crypto.checksum(payload), status=status,
    )


def _campos(conta, nome="Nova"):
    return {
        "account_id": str(conta.id),
        "legal_name": f"{nome} LTDA",
        "trade_name": nome,
        "is_active": True,
    }


# ── 1. A corrida entre o consumer e o beat ───────────────────────────────────

def test_delete_ja_aplicado_nao_apaga_o_registro_recriado(
    como_loja, conta, no_nuvem, no_loja
):
    """A checagem de status precisa acontecer DENTRO da transação.

    Reproduz a corrida real: o consumer enfileira o lote assim que grava na
    inbox e o beat varre a mesma fila a cada 15s, então dois workers seguram o
    MESMO evento. Cada um leu o objeto quando ainda estava RECEIVED; um deles
    aplica e comita primeiro. O outro tem em mãos exatamente o que este teste
    monta: um objeto em memória dizendo RECEIVED sobre uma linha que no banco
    já diz APPLIED.

    O DELETE é o caminho onde isso machuca, e por um motivo específico: ele sai
    de `_aplicar` antes da resolução de conflito, então não existe comparação
    de versão para segurar a segunda passagem. Num UPSERT a versão igual acaba
    salvando por acidente; aqui não há rede.
    """
    restaurante = Restaurant.objects.create(
        account=conta, legal_name="Some LTDA", trade_name="Some"
    )
    evento = _evento_de_entrada(
        conta, no_nuvem, no_loja, entity_id=restaurante.id,
        fields={}, operation=Operation.DELETE,
    )
    assert apply.apply_event(evento) is True

    # O registro volta a existir — a nuvem recriou e o UPSERT já chegou.
    Restaurant.all_objects.filter(pk=restaurante.id).update(deleted_at=None)

    # O "outro worker": a mesma linha, lida antes do commit do primeiro.
    atrasado = SyncEvent.objects.get(pk=evento.pk)
    atrasado.status = EventStatus.RECEIVED

    assert apply.apply_event(atrasado) is False
    restaurante.refresh_from_db()
    assert restaurante.deleted_at is None, (
        "a segunda passagem reaplicou o DELETE e levou o registro recriado"
    )


# ── 2. A retenção apagava o índice de deduplicação ───────────────────────────

def test_retencao_nao_apaga_a_linha_de_entrada_ja_aplicada(como_loja, conta, no_nuvem, no_loja):
    """Apagar a linha de ENTRADA apaga a memória de que aquilo já foi aplicado."""
    evento = _evento_de_entrada(
        conta, no_nuvem, no_loja, entity_id=uuid.uuid4(), fields=_campos(conta)
    )
    antigo = timezone.now() - timezone.timedelta(days=400)
    SyncEvent.objects.filter(pk=evento.pk).update(
        status=EventStatus.ACKNOWLEDGED, acknowledged_at=antigo, applied_at=antigo
    )

    recovery.prune(dias=30)
    assert SyncEvent.objects.filter(pk=evento.pk).exists(), (
        "sem esta linha, um reenvio tardio volta a passar como evento novo"
    )


def test_o_payload_da_entrada_encolhe_mas_a_deduplicacao_continua(
    como_loja, conta, no_nuvem, no_loja
):
    """O conteúdo tem prazo; a memória de já ter aplicado, não."""
    evento = _evento_de_entrada(
        conta, no_nuvem, no_loja, entity_id=uuid.uuid4(), fields=_campos(conta)
    )
    antigo = timezone.now() - timezone.timedelta(days=400)
    SyncEvent.objects.filter(pk=evento.pk).update(
        status=EventStatus.APPLIED, applied_at=antigo
    )

    assert recovery.tombstone_inbound(dias=30) == 1
    evento.refresh_from_db()
    assert evento.payload == {}
    # Passar de novo não recontabiliza: só toca em quem ainda tem payload.
    assert recovery.tombstone_inbound(dias=30) == 0

    # E o reenvio do MESMO event_id continua sendo recusado pela deduplicação.
    repetido = {
        "event_id": str(evento.event_id),
        "sequence": evento.sequence,
        "entity_type": "restaurant",
        "entity_id": evento.entity_id,
        "operation": Operation.UPSERT,
        "payload": {"fields": _campos(conta, "Reenviada")},
    }
    aceitos, _maior = inbox.store_batch(
        [repetido], connection_node=no_nuvem, account_id=conta.id
    )
    assert aceitos == [], "o reenvio tardio foi aceito como evento novo"


# ── 3. Uma loja confirmando a fila de outra ──────────────────────────────────

def test_ack_de_uma_loja_nao_confirma_a_fila_de_outra(como_nuvem, conta, no_nuvem, no_loja):
    """Confirmar é o poder de tirar um evento da fila para sempre."""
    vizinha = SyncNode.objects.create(
        pair_id=uuid.uuid4(), account=conta, node_type=NodeType.LOCAL,
        environment=ENVIRONMENT_DEVELOPMENT, name="Loja vizinha",
        status=NodeStatus.ACTIVE, peer=no_nuvem, is_self=False,
    )
    Restaurant.objects.create(account=conta, legal_name="X LTDA", trade_name="X")
    lote, _ = dispatch.collect_batch(no_nuvem, no_loja)
    assert lote, "o cenário precisa de fila endereçada à primeira loja"
    dispatch.mark_sent(lote)

    dispatch.apply_ack(
        no_nuvem,
        {"acknowledged": [str(e.event_id) for e in lote]},
        target_node=vizinha,
    )

    for evento in lote:
        evento.refresh_from_db()
        assert evento.status == EventStatus.SENT, (
            "a vizinha confirmou um evento que não era endereçado a ela"
        )

    # E o destino certo continua conseguindo confirmar.
    dispatch.apply_ack(
        no_nuvem,
        {"acknowledged": [str(e.event_id) for e in lote]},
        target_node=no_loja,
    )
    for evento in lote:
        evento.refresh_from_db()
        assert evento.status == EventStatus.ACKNOWLEDGED


# ── 4. Segredo escondido dentro de um JSONField ──────────────────────────────

def test_segredo_aninhado_em_json_nao_viaja(conta):
    """`CAMPOS_PROIBIDOS` olhava o nome do campo e parava ali.

    Um `JSONField` chamado `metadata` passa no filtro e leva tudo o que houver
    dentro — inclusive o que a maquininha devolveu e alguém gravou sem reparar.
    """
    from apps.synchronization.services import serialization

    limpo = serialization._limpar_segredos({
        "terminal_name": "Caixa 1",
        "provider_token": "nao-pode-viajar",
        "card": {"last_four": "1234", "api_key": "nao-pode-viajar"},
        "tentativas": [{"password": "nao-pode-viajar", "status": "ok"}],
    })

    assert limpo == {
        "terminal_name": "Caixa 1",
        "card": {"last_four": "1234"},
        "tentativas": [{"status": "ok"}],
    }


def test_json_absurdamente_aninhado_nao_vira_recursao(conta):
    """Um documento montado de propósito não pode derrubar a gravação."""
    from apps.synchronization.services import serialization

    fundo = {"ok": 1}
    for _ in range(200):
        fundo = {"n": fundo}

    resultado = serialization._limpar_segredos(fundo)
    assert resultado  # não estourou a pilha, e é isso que importa


# ── 5. Lote de entrada sem teto ──────────────────────────────────────────────

def test_lote_absurdo_e_recusado_antes_de_gravar(como_loja, conta, no_nuvem, no_loja, settings):
    """Quem valida entrada não conta com a boa vontade da origem."""
    from apps.synchronization.services import inbox

    settings.SYNC_BATCH_MAX_EVENTS = 10
    exagerado = [
        {"event_id": str(uuid.uuid4()), "entity_type": "restaurant",
         "entity_id": str(uuid.uuid4()), "operation": Operation.UPSERT, "payload": {}}
        for _ in range(10 * inbox.FOLGA + 1)
    ]

    antes = SyncEvent.objects.count()
    with pytest.raises(inbox.BatchRejected, match="teto de recepção"):
        inbox.store_batch(exagerado, connection_node=no_nuvem, account_id=conta.id)
    assert SyncEvent.objects.count() == antes, "gravou parte do lote antes de recusar"


def test_lote_dentro_do_teto_continua_passando(como_loja, conta, no_nuvem, no_loja, settings):
    """O limite é o teto do absurdo, não um segundo corte de lote."""
    from apps.synchronization.services import inbox

    settings.SYNC_BATCH_MAX_EVENTS = 10
    normal = [
        {"event_id": str(uuid.uuid4()), "entity_type": "restaurant",
         "entity_id": str(uuid.uuid4()), "operation": Operation.UPSERT,
         "sequence": i + 1, "payload": {"fields": _campos(conta)}}
        for i in range(10)
    ]

    aceitos, _maior = inbox.store_batch(
        normal, connection_node=no_nuvem, account_id=conta.id
    )
    assert len(aceitos) == 10
