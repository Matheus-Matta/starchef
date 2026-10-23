"""Os arquivos de mídia na sincronização: o registro viaja no evento; o arquivo, não.

A foto enviada na loja ia para o disco da loja, e o evento da `Image` levava à
nuvem só o CAMINHO (`accounts/<conta>/images/<id>.jpeg`). A nuvem montava o
link com o próprio domínio — `https://api.starchef.com.br/media/...` — e ele
dava 404: o arquivo nunca tinha saído da loja. A transferência em pedaços
(`files.py`, `files_client.py`) existia inteira e ninguém a chamava.

Aqui fica o que é preciso saber para chamá-la: QUAIS campos são arquivo, se o
arquivo está NESTE servidor e o que já foi transferido. O envio e o download
moram em `midia_envio.py`; quem roda é a loja (`tasks/midia.py`), porque ela
fala com a nuvem e a nuvem não fala com ela.

O caminho do arquivo é o MESMO nos dois servidores, e o link sai dele: basta o
arquivo chegar para o link da nuvem funcionar. Por isso não é preciso apagar o
link "errado" de lado nenhum — e apagar seria pior: a limpeza viraria evento e
apagaria também o caminho na loja, que tem o arquivo.
"""
from datetime import timedelta

from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone

from apps.synchronization.models.transfer import SyncFileTransfer, TransferStatus

#: Depois de uma falha, quanto esperar antes de tentar o mesmo arquivo de novo.
#: Arquivo que falta nos dois lados falharia a cada rodada, para sempre.
ESPERA_DEPOIS_DA_FALHA = timedelta(minutes=30)


def campos_de_midia():
    """`(entrada, campo)` de todo arquivo que o catálogo sincroniza.

    Derivado do catálogo, e não de uma lista à mão: o campo de arquivo novo
    entra sozinho, e o secreto (o certificado A1, em `exclude_fields`) fica de
    fora pela mesma regra que o tira do payload.
    """
    from apps.synchronization.services.registry import registry
    from apps.synchronization.services.serialization import _campo_permitido

    campos = []
    for entrada in registry.entries.values():
        for campo in entrada.model._meta.concrete_fields:
            if (isinstance(campo, models.FileField)
                    and _campo_permitido(campo.name, entrada)
                    and campo.name not in entrada.local_only_fields):
                campos.append((entrada, campo.name))
    return campos


def registros_com_arquivo(entrada, campo):
    gerente = getattr(entrada.model, "all_objects", entrada.model._default_manager)
    return gerente.exclude(**{campo: ""}).exclude(**{f"{campo}__isnull": True})


def existe_aqui(caminho):
    """O arquivo está no armazenamento deste servidor (disco ou bucket)?"""
    if not caminho:
        return False
    try:
        return default_storage.exists(caminho)
    except Exception:  # noqa: BLE001 — bucket fora do ar não é "o arquivo existe"
        return False


def _do_arquivo(entrada, pk, campo, caminho):
    return SyncFileTransfer.objects.filter(
        entity_type=entrada.entity_type, entity_id=str(pk),
        field_name=campo, storage_path=caminho,
    )


def ja_transferido(entrada, pk, campo, caminho):
    return _do_arquivo(entrada, pk, campo, caminho).filter(status=TransferStatus.COMPLETED).exists()


def falhou_ha_pouco(entrada, pk, campo, caminho):
    corte = timezone.now() - ESPERA_DEPOIS_DA_FALHA
    return _do_arquivo(entrada, pk, campo, caminho).filter(
        status=TransferStatus.FAILED, updated_at__gte=corte,
    ).exists()


def registrar(entrada, instancia, campo, caminho, *, origem, destino, status,
              total_bytes=0, checksum="", erro=""):
    """O que a loja fez com o arquivo, para a próxima rodada não refazer."""
    agora = timezone.now()
    return SyncFileTransfer.objects.create(
        account_id=instancia.account_id, source_node=origem, target_node=destino,
        entity_type=entrada.entity_type, entity_id=str(instancia.pk), field_name=campo,
        storage_path=caminho, total_bytes=total_bytes, received_bytes=total_bytes,
        checksum=checksum, status=status, last_error=erro[:2000], attempts=1 if erro else 0,
        completed_at=agora if status == TransferStatus.COMPLETED else None,
    )


def situacao():
    """Por campo: quantos registros têm arquivo e quantos faltam AQUI."""
    linhas = []
    for entrada, campo in campos_de_midia():
        caminhos = list(registros_com_arquivo(entrada, campo).values_list(campo, flat=True))
        faltando = [c for c in caminhos if not existe_aqui(c)]
        linhas.append({"entidade": entrada.entity_type, "campo": campo,
                       "total": len(caminhos), "faltando": faltando})
    return linhas
