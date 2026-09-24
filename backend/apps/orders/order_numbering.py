"""O NÚMERO do pedido: como ele é escolhido, e o que fazer quando é tomado.

Separado de `services.py` porque é uma pergunta só: qual número este pedido
recebe. Lá se decide o que um pedido É; aqui, como ele é numerado — a faixa do
nó, a disputa entre dois caixas e o conserto quando o número escolhido já
pertence a outro.
"""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.tenant import tenant_context
from apps.orders.models import Order


def next_order_sequence(restaurant):
    """O próximo número de pedido deste restaurante, NA FAIXA DESTE NÓ.

    A loja e a nuvem numeram faixas separadas: as duas atendem o mesmo
    restaurante, e enquanto a loja está fora ela não enxerga o que a nuvem
    emitiu. Sem faixas, as duas entregariam o mesmo número, e a conferência de
    caixa do dia encontraria dois "pedido 17". Ver `sequence_ranges`.
    """
    from apps.orders.sequence_ranges import proximo_numero

    with tenant_context(restaurant.account):
        return proximo_numero(Order.objects.filter(restaurant=restaurant))


#: Quantas vezes renumerar antes de desistir. Seis é folga larga: cada rodada
#: relê o máximo já gravado, então duas tentativas já bastam para qualquer
#: disputa real entre dois caixas.
MAX_TENTATIVAS_DE_NUMERO = 6


def _e_colisao_de_numero(erro):
    """O `IntegrityError` é da restrição de número de pedido?

    A mensagem muda com o banco: o PostgreSQL cita o NOME da restrição, o
    SQLite cita as COLUNAS. Qualquer OUTRA violação precisa continuar subindo
    — repetir uma escrita que fere outra regra só transformaria um erro claro
    em seis. "sequence" sozinho não serve de pista: a sincronização também tem
    uma, e gravar o pedido dispara as duas.
    """
    texto = str(erro).lower()
    if "unique_order_sequence_by_branch" in texto:
        return True
    return "orders_order" in texto and "sequence" in texto


def _criar_pedido_numerado(**dados):
    """Grava o pedido, RENUMERANDO quando o número escolhido já foi usado.

    `next_order_sequence` é `Max + 1` lido SEM TRAVA, e entre a leitura e a
    gravação cabe outra escrita: outro caixa abrindo conta no mesmo instante,
    ou a sincronização trazendo do outro nó um pedido que ocupa aquele número.
    Os dois escolhem o mesmo, o banco recusa o segundo — é para isso que a
    restrição existe — e o operador via "Já existe um registro com estes
    dados", que não diz nada sobre o que ele fez nem sobre o que fazer.

    Repetir é o remédio certo aqui: o número seguinte já está livre e a
    segunda tentativa custa uma consulta. Travar a linha do restaurante
    resolveria também, ao preço de serializar TODA abertura de conta daquele
    restaurante pelo tempo inteiro da transação da venda — caro demais para
    escolher um número.

    O `atomic` de dentro é um savepoint: sem ele, a violação envenenaria a
    transação externa e a segunda tentativa morreria antes de tentar.
    """
    restaurant = dados["restaurant"]
    ultima_colisao = None
    for _ in range(MAX_TENTATIVAS_DE_NUMERO):
        try:
            with transaction.atomic():
                return Order.objects.create(
                    sequence=next_order_sequence(restaurant), **dados
                )
        except IntegrityError as erro:
            if not _e_colisao_de_numero(erro):
                raise
            ultima_colisao = erro

    raise ValidationError(
        "Não foi possível numerar o pedido: o número seguinte foi tomado "
        f"{MAX_TENTATIVAS_DE_NUMERO} vezes seguidas. Isso costuma significar "
        "que dois servidores estão numerando na mesma faixa — confira "
        "`SYNC_NODE_TYPE` (a loja usa `local`, o servidor central usa "
        "`cloud`). Tente de novo; nenhum pedido foi aberto."
    ) from ultima_colisao
