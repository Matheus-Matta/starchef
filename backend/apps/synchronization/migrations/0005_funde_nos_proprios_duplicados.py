"""Funde os nós "este" que a versão anterior duplicou.

`ensure_self_node` filtrava por `pair_id`, e como cada matrícula gera um
`pair_id` novo, toda loja adicionada fazia a nuvem criar OUTRO nó `is_self`.
A partir do segundo, `self_node()` passava a escolher um deles arbitrariamente
e o despacho — que filtrava os eventos por `source_node` — devolvia lote vazio
quando a escolha caía no nó que não os originou.

O código já foi corrigido, mas ele não desfaz o que o banco herdou: as
instalações que rodaram a versão com o defeito continuam com o nó extra e com
os eventos presos nele. Esta migração escolhe o mais antigo de cada
`(conta, tipo)` como canônico, repõe todas as referências nele e apaga os
demais. Os eventos parados voltam a sair na primeira conexão.
"""
from django.db import migrations
from django.db.models import Count, Max


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

        for Modelo in (SyncEvent, SyncRun, SyncConflict, SyncFileTransfer):
            Modelo.objects.filter(source_node_id__in=ids_extras).update(source_node=canonico)
            Modelo.objects.filter(target_node_id__in=ids_extras).update(target_node=canonico)
        SyncNode.objects.filter(peer_id__in=ids_extras).update(peer=canonico)

        # A sequência é monotônica por nó: herdar o maior contador evita que o
        # canônico reemita números que os extras já usaram.
        maior = max(n.sequence_counter for n in nos)
        SyncNode.objects.filter(pk=canonico.pk).update(
            sequence_counter=maior,
            last_sent_cursor=max(n.last_sent_cursor for n in nos),
            last_received_cursor=max(n.last_received_cursor for n in nos),
        )
        SyncNode.objects.filter(id__in=ids_extras).delete()


def nao_desfaz(apps, schema_editor):
    """Fundir é destrutivo por natureza; separar de novo não faria sentido."""


class Migration(migrations.Migration):
    dependencies = [("synchronization", "0004_alter_syncnode_peer")]
    operations = [migrations.RunPython(fundir, nao_desfaz)]
