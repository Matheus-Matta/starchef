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

O PEDIDO entra numa versão mais estreita da mesma regra: só quando a linha
VEIO da nuvem. É o pedido que o PDV abriu na nuvem com a loja fora — ele nasce
vazio e ganha o total no primeiro item, e a atualização com o total virava
conflito: a loja mostrava R$ 0,00. Pedido que existe na loja sem nunca ter
descido da nuvem continua conflito, como antes: divergência de dinheiro sem
queda da loja é decisão de uma pessoa.

O CAIXA segue a regra da comanda. A sessão e os movimentos nascem na loja e
sobem; o gerente aprova a sangria, transfere ou libera a sessão no painel da
nuvem, e essa edição precisa descer — antes ela nem descia, e o PDV ficava
"aguardando aprovação" de algo já aprovado.

O TERMINAL é a mesma pergunta no sentido contrário. Ele é `CLOUD` porque
revogar é decisão do painel, mas é a loja que o vê conectar (nome, papel,
`last_seen_at`). Cada conexão virava conflito na nuvem. A nuvem passa a aceitar
a versão da loja quando não tem edição dela que a loja ainda não viu — uma
revogação ainda não entregue continua protegida.

A consulta é EM LOTE: o zerar de 500 comandas chega como um lote de centenas
de eventos, e perguntar item a item seria uma ida ao banco por evento.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models import Count, Max, Q

from apps.synchronization.constants import Direction, EventStatus, NodeType

#: As linhas do cartão.
ENTIDADES_DA_COMANDA = frozenset(
    {"command", "command_item", "command_item_addon", "command_batch"}
)
#: As linhas do pedido, só quando vieram da nuvem. Pagamento fica de fora: ele
#: nunca desvia para a nuvem, então divergência nele não nasceu de queda.
ENTIDADES_DO_PEDIDO = frozenset({"order", "order_item", "order_item_addon", "order_batch"})
#: Sessão e movimentos de caixa: nascem na loja, o painel da nuvem aprova.
ENTIDADES_DO_CAIXA = frozenset({"cash_register", "cash_movement"})
#: Recebidas pela LOJA. As do pedido ainda exigem ter vindo da nuvem.
_NA_LOJA = ENTIDADES_DA_COMANDA | ENTIDADES_DO_PEDIDO | ENTIDADES_DO_CAIXA
#: Recebidas pela NUVEM: a loja é quem vê o terminal conectar.
_NA_NUVEM = frozenset({"pdv_terminal"})
_ENTIDADES = _NA_LOJA | _NA_NUVEM
_CONFIRMADOS = (EventStatus.APPLIED, EventStatus.ACKNOWLEDGED)

#: (tipo, id) -> (envios sem confirmação, versão mais nova que o outro lado
#: conhece, a linha já veio do outro lado)
_retrato = ContextVar("comanda_conflicts_retrato", default=None)


def _em_microssegundos(momento):
    return int(momento.timestamp() * 1_000_000) if momento else 0


def retrato_em_lote(chaves):
    """Duas consultas para o lote inteiro, não uma por evento."""
    from apps.synchronization.models import SyncEvent

    chaves = {(t, str(i)) for t, i in chaves if t in _ENTIDADES}
    if not chaves:
        return {}
    filtro = Q()
    for tipo in {t for t, _ in chaves}:
        filtro |= Q(entity_type=tipo, entity_id__in=[i for t, i in chaves if t == tipo])

    retrato = {chave: (0, 0, False) for chave in chaves}
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
        retrato[chave] = (linha["pendentes"], linha["entregue"] or 0, False)
    # O que veio do outro lado e foi aplicado aqui: o `save` do apply dá à linha a
    # versão "agora", e o `applied_at` é gravado logo depois, na mesma
    # transação — ele cobre a versão que a aplicação deixou.
    entradas = (
        SyncEvent.objects.filter(filtro, direction=Direction.INBOUND, status__in=_CONFIRMADOS)
        .values("entity_type", "entity_id")
        .annotate(aplicado=Max("applied_at"))
    )
    for linha in entradas:
        chave = (linha["entity_type"], linha["entity_id"])
        pendentes, conhecida, _ = retrato[chave]
        retrato[chave] = (pendentes, max(conhecida, _em_microssegundos(linha["aplicado"])), True)
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
    pendentes, conhecida, _ = retrato[chave]
    retrato[chave] = (pendentes, max(conhecida, _em_microssegundos(evento.applied_at)), True)


def _vale_neste_no(entity_type, receiving_node_type):
    if receiving_node_type == NodeType.LOCAL:
        return entity_type in _NA_LOJA
    if receiving_node_type == NodeType.CLOUD:
        return entity_type in _NA_NUVEM
    return False


def outro_lado_ja_conhece_a_versao_local(
    entity_type, receiving_node_type, local_instance, local_version
):
    """Este nó não tem edição desta linha que o outro lado ainda não viu?"""
    if not _vale_neste_no(entity_type, receiving_node_type):
        return False
    if local_instance is None or not local_version:
        return False
    chave = (entity_type, str(local_instance.pk))
    retrato = _retrato.get()
    if retrato is None or chave not in retrato:
        retrato = retrato_em_lote([chave])
    pendentes, conhecida, veio_do_outro_lado = retrato.get(chave, (0, 0, False))
    if pendentes:
        return False
    if entity_type in ENTIDADES_DO_PEDIDO and not veio_do_outro_lado:
        return False
    # Sem evento nenhum, este nó nunca editou a linha (toda escrita local vira
    # evento de saída): não há edição dele a proteger.
    return conhecida == 0 or local_version <= conhecida
