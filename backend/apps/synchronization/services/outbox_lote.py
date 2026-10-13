"""A captura de uma venda inteira, gravada de uma vez — mesmos eventos.

Cada registro salvo virava seu evento na hora (`outbox.record`): relia o
registro, achava os destinos, reservava a sequência e gravava. Numa venda de
10 itens, 942 consultas; na nuvem, a ~6 ms cada, uns 10 s com o cliente no
caixa (medido no alvo de carga com uma loja matriculada).

Dentro de `em_lote()` a captura só ANOTA o registro. No fim do bloco — ainda
dentro da transação de quem chamou, que é o que faz o evento nascer junto com
o dado ou não nascer — os eventos saem juntos: uma leitura por tipo de
registro, a sequência reservada de uma vez e um `bulk_create`. O mesmo
registro salvo várias vezes vira UM evento, com o estado final; a ordem é a da
primeira captura (o pedido antes dos itens, como o destino precisa aplicar).

`descartando()` é para o que vai ser desfeito de qualquer jeito (a simulação
da venda): nenhum evento é montado.
"""
import contextvars
import logging
from collections import defaultdict
from contextlib import contextmanager

from django.db import IntegrityError, connection, models, transaction
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, Operation

logger = logging.getLogger(__name__)

_DESCARTAR = object()
_lote = contextvars.ContextVar("outbox_lote", default=None)


def anotar(instance, operation):
    """`True` quando o lote em curso ficou com o registro (ou o descartou)."""
    pendentes = _lote.get()
    if pendentes is None:
        return False
    if pendentes is _DESCARTAR:
        return True
    chave = (type(instance), instance.pk)
    anterior = pendentes.pop(chave, None) if operation == Operation.DELETE else pendentes.get(chave)
    if anterior is not None and anterior[1] == Operation.CREATE and operation != Operation.DELETE:
        operation = Operation.CREATE  # criado e editado no mesmo lote = criado
    pendentes[chave] = (instance, operation)
    return True


@contextmanager
def em_lote():
    """Junta a captura do bloco e grava os eventos no fim, na mesma transação."""
    if _lote.get() is not None:  # dentro de outro lote: quem abriu grava
        yield
        return
    pendentes = {}
    token = _lote.set(pendentes)
    try:
        yield
    finally:
        _lote.reset(token)
    _gravar(pendentes)  # só sem exceção: com erro, a transação desfaz tudo


@contextmanager
def descartando():
    token = _lote.set(_DESCARTAR)
    try:
        yield
    finally:
        _lote.reset(token)


def _gravar(pendentes):
    if not pendentes:
        return
    from apps.synchronization.services import nodes

    origem = nodes.self_node_or_none()
    if origem is None:
        return
    eventos = _montar(origem, pendentes)
    if eventos:
        _persistir(origem, eventos)


def _montar(origem, pendentes):
    from apps.synchronization.services import nodes, outbox, serialization
    from apps.synchronization.services.registry import registry

    pks = defaultdict(list)
    for (classe, pk), (_, operacao) in pendentes.items():
        if operacao != Operation.DELETE and pk is not None:
            pks[classe].append(pk)
    do_banco = {(classe, obj.pk): obj for classe, lista in pks.items()
                for obj in classe._base_manager.filter(pk__in=lista)}
    destinos_da_conta, eventos = {}, []
    for (classe, pk), (instancia, operacao) in pendentes.items():
        entrada = registry.for_model(classe)
        if entrada is None or not outbox._direcao_permitida(entrada, origem, operation=operacao):
            continue
        alvo = instancia if operacao == Operation.DELETE else do_banco.get((classe, pk), instancia)
        conta = getattr(alvo, "account_id", None) or outbox._account_de(alvo)
        if conta is None:
            continue
        if conta not in destinos_da_conta:
            destinos_da_conta[conta] = nodes.targets_for(origem, conta)
        if not destinos_da_conta[conta]:
            continue
        payload = serialization.build_payload(alvo, entrada, origin_node_id=origem.id)
        if operacao == Operation.DELETE:
            payload["entity_version"] = int(timezone.now().timestamp() * 1_000_000)
        eventos += [(destino, conta, entrada, payload, operacao) for destino in destinos_da_conta[conta]]
    return eventos


def _persistir(origem, eventos):
    from apps.synchronization.models import SyncEvent
    from apps.synchronization.services import crypto, outbox

    try:
        with transaction.atomic():
            sequencias = _reservar(origem, len(eventos))
            SyncEvent.objects.bulk_create([
                SyncEvent(
                    account_id=conta, source_node=origem, target_node=destino, run=None,
                    direction=Direction.OUTBOUND, sequence=sequencia,
                    entity_type=entrada.entity_type, entity_id=payload["entity_id"],
                    operation=operacao, entity_version=payload["entity_version"],
                    payload=payload, payload_checksum=crypto.checksum(payload),
                    status=EventStatus.PENDING,
                )
                for sequencia, (destino, conta, entrada, payload, operacao) in zip(
                    sequencias, eventos, strict=True)
            ])
    except IntegrityError:
        # Colisão de sequência (contador atrás do maior já gravado): o caminho
        # de um em um sabe realinhar. Raro, e o resultado é o mesmo.
        logger.warning("sync: lote de %d eventos colidiu na sequência; um a um.", len(eventos))
        for destino, conta, entrada, payload, operacao in eventos:
            outbox._criar_evento(origem, destino, conta, entrada, payload, operacao, None)


def _reservar(origem, quantos):
    """`quantos` números de evento de uma vez (ver `sequencia_pg.py`)."""
    from apps.synchronization.models import SyncNode
    from apps.synchronization.services import sequencia_pg

    if sequencia_pg.disponivel():
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(%s) FROM generate_series(1, %s)",
                           [sequencia_pg.NOME, quantos])
            return [int(linha[0]) for linha in cursor.fetchall()]
    SyncNode.objects.filter(pk=origem.pk).update(
        sequence_counter=models.F("sequence_counter") + quantos)
    fim = SyncNode.objects.values_list("sequence_counter", flat=True).get(pk=origem.pk)
    return list(range(fim - quantos + 1, fim + 1))
