"""Fundir dois nós que são a mesma loja — e recusar fundir o que não é.

O caso real por trás disto: uma loja que rematriculou ganhou um SEGUNDO nó na
nuvem. A carga inicial ficou apontando para o primeiro e a loja passou a
conectar pelo segundo, então o despacho devolvia lote vazio e centenas de
eventos ficavam em PENDING com `tentativas=0`.
"""
import uuid

import pytest
from django.core.management import CommandError, call_command

from apps.synchronization.constants import (
    Direction,
    EventStatus,
    NodeStatus,
    NodeType,
)
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import crypto, merge_nodes

pytestmark = pytest.mark.django_db


def _no(conta, nome, *, tipo=NodeType.LOCAL, proprio=False, status=NodeStatus.ACTIVE,
        contador=0):
    return SyncNode.objects.create(
        pair_id=uuid.uuid4(), account=conta, node_type=tipo, name=nome,
        status=status, is_self=proprio, sequence_counter=contador,
    )


def _evento(conta, origem, destino, sequencia, *, direction=Direction.OUTBOUND):
    payload = {"fields": {}, "entity_version": 1}
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino, direction=direction,
        sequence=sequencia, entity_type="restaurant", entity_id=str(uuid.uuid4()),
        operation="UPSERT", entity_version=1, payload=payload,
        payload_checksum=crypto.checksum(payload), status=EventStatus.PENDING,
    )


# ── o que ele FAZ ───────────────────────────────────────────────────────────
def test_a_fila_presa_passa_a_apontar_para_o_no_vivo(conta, no_nuvem):
    """O cenário exato da produção: 3 eventos presos no nó abandonado."""
    abandonado = _no(conta, "Loja Centro", status=NodeStatus.PENDING)
    vivo = _no(conta, "Loja Centro")
    presos = [_evento(conta, no_nuvem, abandonado, s) for s in (1, 2, 3)]

    merge_nodes.merge(abandonado, vivo)

    for evento in presos:
        evento.refresh_from_db()
        assert evento.target_node_id == vivo.id
    assert not SyncNode.objects.filter(pk=abandonado.pk).exists()


def test_eventos_originados_sao_renumerados(conta, no_nuvem):
    """Os dois nós têm evento nº 1 e nº 2 — sem renumerar, colidem."""
    origem = _no(conta, "Loja Centro", status=NodeStatus.PENDING, contador=2)
    destino = _no(conta, "Loja Centro", contador=2)
    _evento(conta, destino, no_nuvem, 1)
    _evento(conta, destino, no_nuvem, 2)
    movidos = [_evento(conta, origem, no_nuvem, 1), _evento(conta, origem, no_nuvem, 2)]

    merge_nodes.merge(origem, destino)

    sequencias = sorted(
        SyncEvent.objects.filter(source_node=destino, direction=Direction.OUTBOUND)
        .values_list("sequence", flat=True)
    )
    assert sequencias == [1, 2, 3, 4]
    for evento in movidos:
        evento.refresh_from_db()
    assert [e.sequence for e in movidos] == [3, 4], "devem entrar depois, na ordem"


def test_o_contador_sobe_acima_da_maior_sequencia(conta, no_nuvem):
    origem = _no(conta, "Loja", status=NodeStatus.PENDING, contador=1)
    destino = _no(conta, "Loja", contador=1)
    _evento(conta, destino, no_nuvem, 1)
    _evento(conta, origem, no_nuvem, 1)

    merge_nodes.merge(origem, destino)

    destino.refresh_from_db()
    maior = max(SyncEvent.objects.filter(source_node=destino).values_list("sequence", flat=True))
    assert destino.sequence_counter >= maior


def test_dry_run_nao_grava_nada(conta, no_nuvem):
    abandonado = _no(conta, "Loja", status=NodeStatus.PENDING)
    vivo = _no(conta, "Loja")
    evento = _evento(conta, no_nuvem, abandonado, 1)

    resumo = merge_nodes.merge(abandonado, vivo, dry_run=True)

    assert resumo["eventos_como_destino"] == 1
    evento.refresh_from_db()
    assert evento.target_node_id == abandonado.id
    assert SyncNode.objects.filter(pk=abandonado.pk).exists()


# ── o que ele RECUSA ────────────────────────────────────────────────────────
def test_recusa_fundir_contas_diferentes(conta, outra_conta):
    """A trava mais importante: fundir misturaria dados de dois clientes."""
    a = _no(conta, "Loja")
    b = _no(outra_conta, "Loja")

    with pytest.raises(merge_nodes.MergeRecusada, match="contas diferentes"):
        merge_nodes.merge(a, b)


def test_recusa_fundir_tipos_diferentes(conta, no_nuvem):
    loja = _no(conta, "Loja")
    with pytest.raises(merge_nodes.MergeRecusada, match="Tipos diferentes"):
        merge_nodes.merge(loja, no_nuvem)


def test_recusa_dar_a_identidade_local_a_um_no_remoto(conta, como_loja):
    remoto = _no(conta, "Outra loja")
    with pytest.raises(merge_nodes.MergeRecusada, match="ESTA instalação"):
        merge_nodes.merge(remoto, como_loja)


def test_recusa_fundir_o_no_consigo_mesmo(conta):
    no = _no(conta, "Loja")
    with pytest.raises(merge_nodes.MergeRecusada, match="mesmo nó"):
        merge_nodes.merge(no, no)


# ── candidatos ──────────────────────────────────────────────────────────────
def test_candidatos_agrupa_por_conta_restaurante_e_nome(conta, outra_conta):
    a1 = _no(conta, "Loja Centro", status=NodeStatus.PENDING)
    a2 = _no(conta, "Loja Centro")
    _no(conta, "Loja Shopping")           # sozinho, não é candidato
    _no(outra_conta, "Loja Centro")       # mesmo nome, OUTRA conta

    grupos = merge_nodes.candidatos()

    assert len(grupos) == 1
    (nos,) = grupos.values()
    assert {n.pk for n in nos} == {a1.pk, a2.pk}


def test_candidatos_ignora_o_no_proprio(conta, como_loja):
    """`is_self` é a identidade desta instalação; não entra em fusão sugerida."""
    assert merge_nodes.candidatos() == {}


# ── o comando ───────────────────────────────────────────────────────────────
def test_o_comando_exige_from_e_to(conta):
    with pytest.raises(CommandError, match="--from e --to"):
        call_command("sync_merge_nodes")


def test_o_comando_recusa_id_inexistente(conta):
    vivo = _no(conta, "Loja")
    with pytest.raises(CommandError, match="não existe"):
        call_command("sync_merge_nodes", "--from", str(uuid.uuid4()), "--to", str(vivo.id))


def test_o_comando_funde(conta, no_nuvem):
    abandonado = _no(conta, "Loja", status=NodeStatus.PENDING)
    vivo = _no(conta, "Loja")
    evento = _evento(conta, no_nuvem, abandonado, 1)

    call_command("sync_merge_nodes", "--from", str(abandonado.id), "--to", str(vivo.id))

    evento.refresh_from_db()
    assert evento.target_node_id == vivo.id
    assert not SyncNode.objects.filter(pk=abandonado.pk).exists()


# ── descartar a fila de saída (botão do Admin) ──────────────────────────────
def test_descartar_apaga_so_a_fila_de_saida(conta, no_nuvem):
    """A trava que importa: o que veio da loja NÃO pode ser apagado.

    Um evento INBOUND é uma venda, um pagamento, uma sangria que este lado
    ainda não aplicou. Nenhum botão de Admin pode perder isso.
    """
    from apps.synchronization.services import recovery

    loja = _no(conta, "Loja Centro")
    saindo = [_evento(conta, no_nuvem, loja, s) for s in (1, 2, 3)]
    chegando = _evento(conta, loja, no_nuvem, 1, direction=Direction.INBOUND)

    apagados, _cargas = recovery.discard_outbound(loja)

    assert apagados == 3
    assert not SyncEvent.objects.filter(pk__in=[e.pk for e in saindo]).exists()
    chegando.refresh_from_db()  # continua lá
    assert chegando.direction == Direction.INBOUND


def test_descartar_encerra_a_carga_que_bloquearia_a_proxima(conta, no_nuvem):
    """Sem isto, `Sincronizar tudo` responderia "já existe uma carga"."""
    from apps.synchronization.constants import RunStatus, RunType
    from apps.synchronization.models import SyncRun
    from apps.synchronization.services import recovery

    loja = _no(conta, "Loja Centro")
    carga = SyncRun.objects.create(
        account=conta, source_node=no_nuvem, target_node=loja,
        run_type=RunType.FULL, status=RunStatus.RUNNING,
    )

    _apagados, cancelados = recovery.discard_outbound(loja)

    assert cancelados == 1
    carga.refresh_from_db()
    assert carga.status == RunStatus.CANCELLED
    assert carga.completed_at is not None


def test_descartar_nao_toca_na_fila_de_outro_no(conta, no_nuvem):
    from apps.synchronization.services import recovery

    uma = _no(conta, "Loja A")
    outra = _no(conta, "Loja B")
    da_outra = _evento(conta, no_nuvem, outra, 1)
    _evento(conta, no_nuvem, uma, 2)

    recovery.discard_outbound(uma)

    da_outra.refresh_from_db()
    assert SyncEvent.objects.filter(target_node=outra).count() == 1
