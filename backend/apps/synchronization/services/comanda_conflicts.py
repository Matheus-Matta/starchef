"""A comanda editada na nuvem não é conflito quando a loja não mexeu nela.

`command`, `command_item` & cia. são `LOJA` ("a loja vence") porque o salão é
da loja. Só que a loja RECUSAVA toda versão mais nova vinda da nuvem: o
gerente zerava as comandas no painel web, a loja abria um conflito por item, e
o PDV seguia com os itens — até a versão da loja subir e desfazer o zerar na
nuvem também.

"A loja vence" protege uma edição da loja que a nuvem AINDA NÃO VIU. A
pergunta, então, é: a versão local é uma que a nuvem já conhece? Conhece se
ela foi entregue (evento de saída confirmado) ou se veio da própria nuvem
(evento de entrada aplicado). Edição local que ainda não subiu continua sendo
conflito, e decisão de gente.

A consulta é EM LOTE: o zerar de 500 comandas chega como um lote de centenas
de eventos, e perguntar item a item seria uma ida ao banco por evento.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models import Count, Max, Q

from apps.synchronization.constants import Direction, EventStatus, NodeType

#: As linhas do cartão. Pedido e pagamento NÃO: divergência de dinheiro sem
#: queda da loja segue sendo decisão de uma pessoa.
ENTIDADES_DA_COMANDA = frozenset(
    {"command", "command_item", "command_item_addon", "command_batch"}
)
_CONFIRMADOS = (EventStatus.APPLIED, EventStatus.ACKNOWLEDGED)

#: (tipo, id) -> (envios sem confirmação, versão mais nova que a nuvem conhece)
_retrato = ContextVar("comanda_conflicts_retrato", default=None)


def _em_microssegundos(momento):
    return int(momento.timestamp() * 1_000_000) if momento else 0


def retrato_em_lote(chaves):
    """Duas consultas para o lote inteiro, não uma por evento."""
    from apps.synchronization.models import SyncEvent

    chaves = {(t, str(i)) for t, i in chaves if t in ENTIDADES_DA_COMANDA}
    if not chaves:
        return {}
    filtro = Q()
    for tipo in {t for t, _ in chaves}:
        filtro |= Q(entity_type=tipo, entity_id__in=[i for t, i in chaves if t == tipo])

    retrato = {chave: (0, 0) for chave in chaves}
    saidas = (
        SyncEvent.objects.filter(filtro, direction=Direction.OUTBOUND)
        .values("entity_type", "entity_id")
        .annotate(
            pendentes=Count("pk", filter=~Q(status__in=_CONFIRMADOS)),
            entregue=Max("entity_version", filter=Q(status__in=_CONFIRMADOS)),
        )
    )
    for linha in saidas:
        chave = (linha["entity_type"], linha["entity_id"])
        retrato[chave] = (linha["pendentes"], linha["entregue"] or 0)
    # O que veio da nuvem e foi aplicado aqui: o `save` do apply dá à linha a
    # versão "agora", e o `applied_at` é gravado logo depois, na mesma
    # transação — ele cobre a versão que a aplicação deixou.
    entradas = (
        SyncEvent.objects.filter(filtro, direction=Direction.INBOUND, status__in=_CONFIRMADOS)
        .values("entity_type", "entity_id")
        .annotate(aplicado=Max("applied_at"))
    )
    for linha in entradas:
        chave = (linha["entity_type"], linha["entity_id"])
        pendentes, conhecida = retrato[chave]
        retrato[chave] = (pendentes, max(conhecida, _em_microssegundos(linha["aplicado"])))
    return retrato


@contextmanager
def lote(eventos):
    """Calcula o retrato do lote uma vez; `decide` lê dele em vez do banco."""
    token = _retrato.set(retrato_em_lote((e.entity_type, e.entity_id) for e in eventos))
    try:
        yield
    finally:
        _retrato.reset(token)


def anotar_aplicado(evento):
    """O lote aplicou esta versão: o retrato passa a conhecê-la.

    Sem isto, o MESMO item duas vezes no lote (cancelado e depois encerrado)
    teria a segunda versão julgada contra o retrato de antes da primeira — e
    a versão que a própria aplicação acabou de gravar viraria "edição da loja".
    """
    retrato = _retrato.get()
    chave = (evento.entity_type, str(evento.entity_id))
    if retrato is None or chave not in retrato:
        return
    pendentes, conhecida = retrato[chave]
    retrato[chave] = (pendentes, max(conhecida, _em_microssegundos(evento.applied_at)))


def nuvem_ja_conhece_a_versao_local(entity_type, receiving_node_type, local_instance, local_version):
    """A loja não tem edição desta linha que a nuvem ainda não viu?"""
    if entity_type not in ENTIDADES_DA_COMANDA or receiving_node_type != NodeType.LOCAL:
        return False
    if local_instance is None or not local_version:
        return False
    chave = (entity_type, str(local_instance.pk))
    retrato = _retrato.get()
    if retrato is None or chave not in retrato:
        retrato = retrato_em_lote([chave])
    pendentes, conhecida = retrato.get(chave, (0, 0))
    if pendentes:
        return False
    # Sem evento nenhum, a loja nunca editou a linha (toda escrita local vira
    # evento de saída): não há edição dela a proteger.
    return conhecida == 0 or local_version <= conhecida
