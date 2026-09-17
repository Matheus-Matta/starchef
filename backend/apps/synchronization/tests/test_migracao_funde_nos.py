"""A fusão dos nós "este" duplicados — com a renumeração da sequência.

Este arquivo existe por causa de um erro em produção: a primeira versão da
migração fazia `UPDATE source_node` cego e batia em
`sync_unique_sequence_per_source` no primeiro evento repetido, porque cada nó
conta a própria sequência a partir do 1.
"""
import datetime
import importlib
import uuid

import pytest
from django.apps import apps as registro
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, NodeStatus, NodeType
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import crypto

pytestmark = pytest.mark.django_db

migracao = importlib.import_module(
    "apps.synchronization.migrations.0005_funde_nos_proprios_duplicados"
)


#: Ponto fixo no tempo para as idades dos nós do teste.
AGORA = timezone.now()


def _no(conta, nome, *, tipo=NodeType.CLOUD, proprio=True, contador=0, idade_h=0):
    """Cria um nó com `created_at` EXPLÍCITO.

    A migração escolhe o canônico por `created_at`, e `auto_now_add` carimba
    todos os nós do teste no mesmo tick. Com empate o desempate cai no `id`,
    que é UUID aleatório — e o teste passa a depender de sorteio. Fixar a
    idade aqui é o que torna "o mais antigo vence" verificável.
    """
    no = SyncNode.objects.create(
        pair_id=uuid.uuid4(), account=conta, node_type=tipo, name=nome,
        status=NodeStatus.ACTIVE, is_self=proprio, sequence_counter=contador,
    )
    SyncNode.objects.filter(pk=no.pk).update(
        created_at=AGORA - datetime.timedelta(hours=idade_h)
    )
    no.refresh_from_db(fields=["created_at"])
    return no


def _evento(conta, origem, destino, sequencia, *, direction=Direction.OUTBOUND):
    payload = {"fields": {}, "entity_version": 1}
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino, direction=direction,
        sequence=sequencia, entity_type="restaurant", entity_id=str(uuid.uuid4()),
        operation="UPSERT", entity_version=1, payload=payload,
        payload_checksum=crypto.checksum(payload), status=EventStatus.PENDING,
    )


def test_funde_renumerando_a_sequencia(conta):
    """Os dois nós têm evento nº 1 e nº 2 — era exatamente aqui que estourava."""
    canonico = _no(conta, "Nuvem A", contador=2, idade_h=2)
    intruso = _no(conta, "Nuvem B", contador=2, idade_h=1)
    loja = _no(conta, "Loja", tipo=NodeType.LOCAL, proprio=False)

    _evento(conta, canonico, loja, 1)
    _evento(conta, canonico, loja, 2)
    do_intruso = [_evento(conta, intruso, loja, 1), _evento(conta, intruso, loja, 2)]

    migracao.fundir(registro, None)

    assert not SyncNode.objects.filter(pk=intruso.pk).exists()
    assert SyncNode.objects.filter(account=conta, node_type=NodeType.CLOUD, is_self=True).count() == 1

    # Os quatro eventos vivem sob o canônico, com sequências distintas.
    sequencias = sorted(
        SyncEvent.objects.filter(source_node=canonico, direction=Direction.OUTBOUND)
        .values_list("sequence", flat=True)
    )
    assert sequencias == [1, 2, 3, 4]

    # E os que mudaram de dono entraram DEPOIS, na ordem em que estavam.
    for evento in do_intruso:
        evento.refresh_from_db()
    assert [e.sequence for e in do_intruso] == [3, 4]


def test_o_contador_fica_acima_da_maior_sequencia(conta):
    """Senão o próximo evento nasce colidindo com um dos renumerados."""
    canonico = _no(conta, "Nuvem A", contador=1, idade_h=2)
    intruso = _no(conta, "Nuvem B", contador=1, idade_h=1)
    loja = _no(conta, "Loja", tipo=NodeType.LOCAL, proprio=False)
    _evento(conta, canonico, loja, 1)
    _evento(conta, intruso, loja, 1)

    migracao.fundir(registro, None)

    canonico.refresh_from_db()
    maior = max(
        SyncEvent.objects.filter(source_node=canonico).values_list("sequence", flat=True)
    )
    assert canonico.sequence_counter >= maior


def test_cada_direcao_e_renumerada_separadamente(conta):
    """A unicidade é por (origem, direção): INBOUND e OUTBOUND não se misturam."""
    canonico = _no(conta, "Nuvem A", idade_h=2)
    intruso = _no(conta, "Nuvem B", idade_h=1)
    loja = _no(conta, "Loja", tipo=NodeType.LOCAL, proprio=False)
    _evento(conta, canonico, loja, 1, direction=Direction.OUTBOUND)
    _evento(conta, canonico, loja, 1, direction=Direction.INBOUND)
    _evento(conta, intruso, loja, 1, direction=Direction.OUTBOUND)
    _evento(conta, intruso, loja, 1, direction=Direction.INBOUND)

    migracao.fundir(registro, None)

    for direcao in (Direction.OUTBOUND, Direction.INBOUND):
        sequencias = sorted(
            SyncEvent.objects.filter(source_node=canonico, direction=direcao)
            .values_list("sequence", flat=True)
        )
        assert sequencias == [1, 2], f"direção {direcao} renumerada errado"


def test_o_destino_tambem_e_reposto(conta):
    """Eventos apontando para o nó extra como DESTINO não podem ficar órfãos."""
    canonico = _no(conta, "Nuvem A", idade_h=2)
    intruso = _no(conta, "Nuvem B", idade_h=1)
    origem = _no(conta, "Loja", tipo=NodeType.LOCAL, proprio=False)
    evento = _evento(conta, origem, intruso, 1, direction=Direction.INBOUND)

    migracao.fundir(registro, None)

    evento.refresh_from_db()
    assert evento.target_node_id == canonico.id


def test_sem_duplicata_nao_mexe_em_nada(conta):
    canonico = _no(conta, "Nuvem A")
    loja = _no(conta, "Loja", tipo=NodeType.LOCAL, proprio=False)
    evento = _evento(conta, canonico, loja, 7)

    migracao.fundir(registro, None)

    evento.refresh_from_db()
    assert evento.sequence == 7
    assert SyncNode.objects.count() == 2
