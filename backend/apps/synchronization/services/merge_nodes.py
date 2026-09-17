"""Funde dois SyncNode que são, na verdade, a mesma instalação.

O caso real: uma loja que rematriculou antes da correção que faz o backend
local reler as credenciais gravadas. Sem `existing_node_id` no pedido, a nuvem
criava OUTRO nó para a mesma loja (`enrollment._provisionar`). Ficam dois —
um que nunca conectou e outro ativo — e a carga inicial, gerada para o
primeiro, nunca alcança o segundo: o despacho filtra pelo destino, a consulta
volta vazia, e a loja recebe `pending: 0` para sempre, sem erro em lugar
nenhum.

Fundir não é adivinhação: quem decide que os dois nós são a mesma loja é a
pessoa que roda `manage.py sync_merge_nodes`. Duas lojas podem legitimamente
ter o mesmo nome, então casar por nome automaticamente seria pior que o
problema.

A parte delicada é a **sequência**. `sequence` é única por
`(source_node, direction)` e cada nó conta a partir do 1: mover eventos com um
`UPDATE` cego viola `sync_unique_sequence_per_source` no primeiro choque. Os
eventos que mudam de dono entram depois dos que o destino já tinha,
preservando a ordem relativa entre si — a ordem é o que garante que o pai seja
aplicado antes do filho do outro lado.
"""
import logging

from django.db import transaction
from django.db.models import Max

from apps.synchronization.constants import NodeType
from apps.synchronization.models import (
    SyncConflict,
    SyncEvent,
    SyncFileTransfer,
    SyncNode,
    SyncRun,
)

logger = logging.getLogger(__name__)

#: Estados em que a transferência ainda ocupa a chave única parcial.
TRANSFERENCIAS_ABERTAS = ["PENDING", "RECEIVING", "VALIDATING"]


class MergeRecusada(Exception):
    """A fusão pedida não é segura, e o motivo vem junto."""


def candidatos(account=None):
    """Grupos de nós LOCAL que parecem ser a mesma loja.

    Serve para o operador OLHAR antes de decidir — nada aqui funde nada.
    O agrupamento é por `(conta, restaurante, nome)`, e o `restaurant` nulo
    (loja matriculada sem restaurante definido) não impede o agrupamento,
    apenas o torna menos específico.
    """
    consulta = SyncNode.objects.filter(node_type=NodeType.LOCAL, is_self=False)
    if account is not None:
        consulta = consulta.filter(account=account)

    grupos = {}
    for no in consulta.order_by("created_at", "id"):
        chave = (no.account_id, no.restaurant_id, no.name)
        grupos.setdefault(chave, []).append(no)
    return {chave: nos for chave, nos in grupos.items() if len(nos) > 1}


def merge(origem, destino, *, dry_run=False):
    """Move tudo de `origem` para `destino` e apaga `origem`.

    Devolve um dicionário com o que foi (ou seria) movido.
    """
    _validar(origem, destino)

    with transaction.atomic():
        resumo = {
            "eventos_como_origem": 0,
            "eventos_como_destino": 0,
            "runs": 0,
            "conflitos": 0,
            "transferencias": 0,
            "transferencias_descartadas": 0,
            "maior_sequencia": 0,
        }

        movidos, maior = _mover_eventos_por_origem(origem, destino, dry_run=dry_run)
        resumo["eventos_como_origem"] = movidos
        resumo["maior_sequencia"] = maior

        alvo = SyncEvent.objects.filter(target_node=origem)
        resumo["eventos_como_destino"] = alvo.count()
        if not dry_run:
            alvo.update(target_node=destino)

        for Modelo, chave in ((SyncRun, "runs"), (SyncConflict, "conflitos")):
            como_origem = Modelo.objects.filter(source_node=origem)
            como_destino = Modelo.objects.filter(target_node=origem)
            resumo[chave] = como_origem.count() + como_destino.count()
            if not dry_run:
                como_origem.update(source_node=destino)
                como_destino.update(target_node=destino)

        movidas, descartadas = _mover_transferencias(origem, destino, dry_run=dry_run)
        resumo["transferencias"] = movidas
        resumo["transferencias_descartadas"] = descartadas

        if not dry_run:
            SyncNode.objects.filter(peer=origem).update(peer=destino)
            # O contador precisa ficar acima da maior sequência que existe
            # agora, senão o próximo evento nasce colidindo com um dos que
            # acabaram de ser renumerados.
            SyncNode.objects.filter(pk=destino.pk).update(
                sequence_counter=max(
                    destino.sequence_counter, origem.sequence_counter, maior
                ),
                last_sent_cursor=max(destino.last_sent_cursor, origem.last_sent_cursor),
                last_received_cursor=max(
                    destino.last_received_cursor, origem.last_received_cursor
                ),
            )
            SyncNode.objects.filter(pk=origem.pk).delete()
            logger.warning(
                "sync: nó %s fundido em %s (%s eventos reapontados)",
                origem.id, destino.id,
                resumo["eventos_como_origem"] + resumo["eventos_como_destino"],
            )

        if dry_run:
            transaction.set_rollback(True)

    return resumo


def _validar(origem, destino):
    if origem.pk == destino.pk:
        raise MergeRecusada("Origem e destino são o mesmo nó.")
    if origem.account_id != destino.account_id:
        raise MergeRecusada(
            "Os nós são de contas diferentes. Fundir misturaria dados de dois "
            "clientes — é exatamente o que a separação por conta existe para impedir."
        )
    if origem.node_type != destino.node_type:
        raise MergeRecusada(
            f"Tipos diferentes: {origem.node_type} e {destino.node_type}. "
            "Um nó de nuvem não é a mesma instalação que um nó de loja."
        )
    if destino.is_self and not origem.is_self:
        raise MergeRecusada(
            "O destino representa ESTA instalação e a origem não. "
            "Fundir daria a identidade local a um nó remoto."
        )


def _mover_eventos_por_origem(origem, destino, *, dry_run):
    """Renumera e repõe os eventos que `origem` originou.

    Devolve `(quantos, maior_sequencia_no_destino)`.
    """
    total = 0
    maior_geral = 0
    direcoes = (
        SyncEvent.objects.filter(source_node=origem)
        .values_list("direction", flat=True)
        .distinct()
    )
    for direcao in list(direcoes):
        ocupado = SyncEvent.objects.filter(
            source_node=destino, direction=direcao
        ).aggregate(maior=Max("sequence"))["maior"] or 0

        proxima = ocupado + 1
        movendo = SyncEvent.objects.filter(
            source_node=origem, direction=direcao
        ).order_by("sequence")

        lote = []
        for evento in movendo.iterator(chunk_size=500):
            evento.source_node = destino
            evento.sequence = proxima
            proxima += 1
            lote.append(evento)
        if lote and not dry_run:
            SyncEvent.objects.bulk_update(
                lote, ["source_node", "sequence"], batch_size=500
            )
        total += len(lote)
        maior_geral = max(maior_geral, proxima - 1)

    return total, maior_geral


def _mover_transferencias(origem, destino, *, dry_run):
    """Repõe as transferências, descartando a que colidiria com uma aberta.

    A chave única parcial é `(target_node, storage_path, checksum)` entre as
    abertas. Se o destino já tem uma transferência aberta do mesmo arquivo, a
    da origem é redundante: apagá-la não perde nada, porque o arquivo é
    retransmitido do zero na próxima tentativa.
    """
    como_origem = SyncFileTransfer.objects.filter(source_node=origem)
    movidas = como_origem.count()
    if not dry_run:
        como_origem.update(source_node=destino)

    descartadas = 0
    for transferencia in SyncFileTransfer.objects.filter(target_node=origem):
        colide = transferencia.status in TRANSFERENCIAS_ABERTAS and (
            SyncFileTransfer.objects.filter(
                target_node=destino,
                storage_path=transferencia.storage_path,
                checksum=transferencia.checksum,
                status__in=TRANSFERENCIAS_ABERTAS,
            ).exists()
        )
        if colide:
            descartadas += 1
            if not dry_run:
                transferencia.delete()
        else:
            movidas += 1
            if not dry_run:
                SyncFileTransfer.objects.filter(pk=transferencia.pk).update(
                    target_node=destino
                )

    return movidas, descartadas
