"""Aviso por destino, e prazo de validade para fila que ninguém busca.

Dois defeitos fecham aqui, e os dois produziam o mesmo sintoma: a loja
conectada, autenticada, com eventos endereçados a ela — e silêncio absoluto,
sem erro em lugar nenhum.
"""
import uuid

import pytest
from django.utils import timezone

from apps.synchronization.constants import (
    Direction,
    EventStatus,
    NodeStatus,
    NodeType,
)
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import crypto, staleness

pytestmark = pytest.mark.django_db


def _no(conta, nome, *, status=NodeStatus.ACTIVE, visto=None, nascido_ha_dias=0,
        restaurante=None):
    no = SyncNode.objects.create(
        pair_id=uuid.uuid4(), account=conta, node_type=NodeType.LOCAL, name=nome,
        status=status, is_self=False, last_seen_at=visto, restaurant=restaurante,
    )
    if nascido_ha_dias:
        SyncNode.objects.filter(pk=no.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=nascido_ha_dias)
        )
        no.refresh_from_db()
    return no


def _evento(conta, origem, destino, sequencia, *, direction=Direction.OUTBOUND):
    payload = {"fields": {}, "entity_version": 1}
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino, direction=direction,
        sequence=sequencia, entity_type="restaurant", entity_id=str(uuid.uuid4()),
        operation="UPSERT", entity_version=1, payload=payload,
        payload_checksum=crypto.checksum(payload), status=EventStatus.PENDING,
    )


# ── o prazo ─────────────────────────────────────────────────────────────────
def test_no_que_nunca_conectou_expira_depois_do_prazo(conta, no_nuvem, settings):
    """`last_seen_at` NULL era invisível para a reconciliação — a comparação
    de data nunca casa com NULL, e o nó problemático é justamente esse."""
    settings.SYNC_STALE_NEVER_SEEN_DAYS = 7
    abandonado = _no(conta, "Loja", status=NodeStatus.PENDING, visto=None,
                     nascido_ha_dias=10)
    _evento(conta, no_nuvem, abandonado, 1)

    resultado = staleness.expirar_filas()

    assert resultado["nos"] == 1
    assert resultado["eventos"] == 1
    assert not SyncEvent.objects.filter(target_node=abandonado).exists()


def test_no_recem_criado_que_ainda_nao_conectou_e_poupado(conta, no_nuvem, settings):
    """Uma instalação subindo agora não pode perder a carga dela."""
    settings.SYNC_STALE_NEVER_SEEN_DAYS = 7
    novo = _no(conta, "Loja", status=NodeStatus.PENDING, visto=None, nascido_ha_dias=1)
    _evento(conta, no_nuvem, novo, 1)

    resultado = staleness.expirar_filas()

    assert resultado["nos"] == 0
    assert SyncEvent.objects.filter(target_node=novo).count() == 1


def test_no_calado_ha_muito_tempo_expira(conta, no_nuvem, settings):
    settings.SYNC_STALE_SILENT_DAYS = 30
    calado = _no(conta, "Loja", visto=timezone.now() - timezone.timedelta(days=45))
    _evento(conta, no_nuvem, calado, 1)

    assert staleness.expirar_filas()["eventos"] == 1


def test_no_visto_agora_nao_perde_nada(conta, no_nuvem, settings):
    settings.SYNC_STALE_SILENT_DAYS = 30
    vivo = _no(conta, "Loja", visto=timezone.now())
    _evento(conta, no_nuvem, vivo, 1)

    assert staleness.expirar_filas()["nos"] == 0
    assert SyncEvent.objects.filter(target_node=vivo).count() == 1


def test_expirar_nunca_apaga_o_que_veio_da_loja(conta, no_nuvem, settings):
    """A trava que importa: INBOUND é venda, pagamento, sangria."""
    settings.SYNC_STALE_NEVER_SEEN_DAYS = 7
    abandonado = _no(conta, "Loja", status=NodeStatus.PENDING, nascido_ha_dias=10)
    _evento(conta, no_nuvem, abandonado, 1)
    da_loja = _evento(conta, abandonado, no_nuvem, 1, direction=Direction.INBOUND)

    staleness.expirar_filas()

    da_loja.refresh_from_db()
    assert da_loja.direction == Direction.INBOUND


def test_dry_run_conta_sem_apagar(conta, no_nuvem, settings):
    settings.SYNC_STALE_NEVER_SEEN_DAYS = 7
    abandonado = _no(conta, "Loja", status=NodeStatus.PENDING, nascido_ha_dias=10)
    _evento(conta, no_nuvem, abandonado, 1)

    resultado = staleness.expirar_filas(dry_run=True)

    assert resultado["eventos"] == 1
    assert SyncEvent.objects.filter(target_node=abandonado).count() == 1


def test_no_revogado_expira_sem_esperar_prazo(conta, no_nuvem):
    revogado = _no(conta, "Loja", status=NodeStatus.REVOKED, visto=timezone.now())
    _evento(conta, no_nuvem, revogado, 1)

    assert staleness.expirar_filas()["eventos"] == 1


# ── a rematrícula supera a ficha antiga ─────────────────────────────────────
def test_rematricula_descarta_a_fila_da_ficha_antiga(conta, no_nuvem):
    """O cenário da produção: a loja passa a conectar por outro nó."""
    antigo = _no(conta, "Loja Centro", status=NodeStatus.PENDING)
    for s in (1, 2, 3):
        _evento(conta, no_nuvem, antigo, s)
    novo = _no(conta, "Loja Centro")

    superados, eventos = staleness.superar_nos_irmaos(novo)

    assert (superados, eventos) == (1, 3)
    antigo.refresh_from_db()
    assert antigo.status == NodeStatus.REVOKED and not antigo.is_active


def test_rematricula_nunca_atravessa_conta(conta, outra_conta, no_nuvem):
    """Superar o nó de OUTRO cliente seria apagar a fila dele."""
    de_outro = _no(outra_conta, "Loja Centro")
    novo = _no(conta, "Loja Centro")

    superados, _eventos = staleness.superar_nos_irmaos(novo)

    assert superados == 0
    de_outro.refresh_from_db()
    assert de_outro.status == NodeStatus.ACTIVE


def test_rematricula_nao_toca_em_outra_loja_da_mesma_conta(conta, no_nuvem):
    outra_loja = _no(conta, "Loja Shopping")
    _evento(conta, no_nuvem, outra_loja, 1)
    novo = _no(conta, "Loja Centro")

    staleness.superar_nos_irmaos(novo)

    outra_loja.refresh_from_db()
    assert outra_loja.status == NodeStatus.ACTIVE
    assert SyncEvent.objects.filter(target_node=outra_loja).count() == 1
