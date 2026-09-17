"""Funde os nós "este" que a versão anterior duplicou.

`ensure_self_node` filtrava por `pair_id`, e como cada matrícula gera um
`pair_id` novo, toda loja adicionada fazia a nuvem criar OUTRO nó `is_self`.
A partir do segundo, `self_node()` passava a escolher um deles arbitrariamente
e o despacho — que filtrava os eventos por `source_node` — devolvia lote vazio
quando a escolha caía no nó que não os originou.

O código já foi corrigido, mas ele não desfaz o que o banco herdou. Esta
migração escolhe o mais antigo de cada `(conta, tipo)` como canônico, repõe as
referências nele e apaga os demais.

**A sequência precisa ser renumerada, não movida.** `sequence` é única por
`(source_node, direction)` e cada nó começa a contar do 1 — os dois têm um
evento nº 1, nº 2, nº 3. Um `UPDATE source_node` cego viola
`sync_unique_sequence_per_source` no primeiro choque. Os eventos que mudam de
dono entram, então, DEPOIS dos que o canônico já tinha, preservando a ordem
relativa entre si: a ordem é o que garante que o pai seja aplicado antes do
filho do outro lado.
"""
from django.db import migrations
from django.db.models import Count, Max

#: Estados em que a transferência ainda ocupa a chave única parcial.
TRANSFERENCIAS_ABERTAS = ["PENDING", "RECEIVING", "VALIDATING"]


def fundir(apps, _schema_editor):
    SyncNode = apps.get_model("synchronization", "SyncNode")
    SyncEvent = apps.get_model("synchronization", "SyncEvent")
    SyncRun = apps.get_model("synchronization", "SyncRun")
    SyncConflict = apps.get_model("synchronization", "SyncConflict")
    SyncFileTransfer = apps.get_model("synchronization", "SyncFileTransfer")

    duplicados = (
        SyncNode.objects.filter(is_self=True)
        .values("account_id", "node_type")
        .annotate(quantos=Count("id"))
        .filter(quantos__gt=1)
    )

    for grupo in duplicados:
        nos = list(
            SyncNode.objects.filter(
                account_id=grupo["account_id"], node_type=grupo["node_type"], is_self=True
            ).order_by("created_at", "id")
        )
        canonico, extras = nos[0], nos[1:]
        ids_extras = [n.id for n in extras]

        maior_sequencia = _mover_eventos(SyncEvent, canonico, ids_extras)
        _mover_transferencias(SyncFileTransfer, canonico, ids_extras)

        for Modelo in (SyncRun, SyncConflict):
            Modelo.objects.filter(source_node_id__in=ids_extras).update(source_node=canonico)
            Modelo.objects.filter(target_node_id__in=ids_extras).update(target_node=canonico)
        SyncNode.objects.filter(peer_id__in=ids_extras).update(peer=canonico)

        # O contador precisa ficar acima da maior sequência que existe agora,
        # senão o próximo evento nasce colidindo com um dos que acabaram de
        # ser renumerados.
        SyncNode.objects.filter(pk=canonico.pk).update(
            sequence_counter=max([n.sequence_counter for n in nos] + [maior_sequencia]),
            last_sent_cursor=max(n.last_sent_cursor for n in nos),
            last_received_cursor=max(n.last_received_cursor for n in nos),
        )
        SyncNode.objects.filter(id__in=ids_extras).delete()


def _mover_eventos(SyncEvent, canonico, ids_extras):
    """Repõe os eventos no canônico dando a cada um uma sequência livre.

    Devolve a maior sequência que o canônico passou a ter.
    """
    # O destino não tem restrição de unicidade: repor é um update simples.
    SyncEvent.objects.filter(target_node_id__in=ids_extras).update(target_node=canonico)

    maior_geral = 0
    direcoes = (
        SyncEvent.objects.filter(source_node_id__in=ids_extras)
        .values_list("direction", flat=True)
        .distinct()
    )
    for direcao in list(direcoes):
        ocupado = SyncEvent.objects.filter(
            source_node=canonico, direction=direcao
        ).aggregate(maior=Max("sequence"))["maior"] or 0

        proxima = ocupado + 1
        # `source_node_id` primeiro mantém juntos os eventos de cada nó extra;
        # `sequence` preserva a ordem original dentro de cada um.
        movendo = (
            SyncEvent.objects.filter(source_node_id__in=ids_extras, direction=direcao)
            .order_by("source_node_id", "sequence")
        )
        lote = []
        for evento in movendo.iterator(chunk_size=500):
            evento.source_node = canonico
            evento.sequence = proxima
            proxima += 1
            lote.append(evento)
        if lote:
            SyncEvent.objects.bulk_update(lote, ["source_node", "sequence"], batch_size=500)
        maior_geral = max(maior_geral, proxima - 1)

    return maior_geral


def _mover_transferencias(SyncFileTransfer, canonico, ids_extras):
    """Repõe as transferências, descartando a que colidiria com uma aberta.

    A chave única parcial é `(target_node, storage_path, checksum)` entre as
    abertas. Se o canônico já tem uma transferência aberta do mesmo arquivo, a
    do nó extra é redundante: apagá-la não perde nada, porque o arquivo é
    retransmitido do zero na próxima tentativa.
    """
    SyncFileTransfer.objects.filter(source_node_id__in=ids_extras).update(source_node=canonico)

    for transferencia in SyncFileTransfer.objects.filter(target_node_id__in=ids_extras):
        colide = transferencia.status in TRANSFERENCIAS_ABERTAS and (
            SyncFileTransfer.objects.filter(
                target_node=canonico,
                storage_path=transferencia.storage_path,
                checksum=transferencia.checksum,
                status__in=TRANSFERENCIAS_ABERTAS,
            ).exists()
        )
        if colide:
            transferencia.delete()
        else:
            SyncFileTransfer.objects.filter(pk=transferencia.pk).update(target_node=canonico)


def nao_desfaz(apps, schema_editor):
    """Fundir é destrutivo por natureza; separar de novo não faria sentido."""


class Migration(migrations.Migration):
    dependencies = [("synchronization", "0004_alter_syncnode_peer")]
    operations = [migrations.RunPython(fundir, nao_desfaz)]
