"""A sequência do nó: reservar o número e consertar quando ele desalinha.

Separado de `outbox.py` porque são duas perguntas diferentes: lá se decide O
QUE vira evento; aqui se resolve COMO ele é numerado, e o que fazer quando o
contador e os eventos discordam.
"""
import logging

from apps.synchronization.constants import Direction

logger = logging.getLogger(__name__)


#: Quantas vezes tentar antes de desistir. Duas bastam: a primeira colisão já
#: realinha o contador acima de tudo que existe.
MAX_TENTATIVAS_DE_SEQUENCIA = 3


def realinhar_contador(origem):
    """Põe o contador do nó à frente do maior evento que ele já gravou.

    O contador (`SyncNode.sequence_counter`) e os eventos são duas fontes para
    o MESMO número, e elas saem de sincronia sem ninguém reclamar: um banco
    restaurado de um backup mais antigo que os eventos, um nó recriado, uma
    importação que gravou sequência explícita.

    A partir daí TODA escrita sincronizada do nó colide — abrir um pedido,
    lançar um item, receber um pagamento —, e o operador vê "já existe um
    registro com estes dados" em cima de um gesto que não tem nada de
    duplicado. Nada indica onde procurar, e o erro não passa sozinho.

    Realinhar na primeira colisão conserta o nó de uma vez: a próxima
    sequência nasce acima de tudo que existe. O `__lt` impede que duas
    transações simultâneas puxem o contador para trás.
    """
    from django.db.models import Max

    from apps.synchronization.models import SyncEvent, SyncNode

    maior = SyncEvent.objects.filter(
        source_node=origem, direction=Direction.OUTBOUND
    ).aggregate(valor=Max("sequence"))["valor"] or 0
    SyncNode.objects.filter(pk=origem.pk, sequence_counter__lt=maior).update(
        sequence_counter=maior
    )
    origem.refresh_from_db(fields=["sequence_counter"])
    logger.warning(
        "sync: contador do nó %s estava atrás dos eventos; realinhado em %s",
        origem.pk, maior,
    )


def e_colisao_de_sequencia(erro):
    """A violação é da sequência do nó? Outra regra precisa continuar subindo.

    Os dois bancos contam a mesma coisa de jeitos diferentes: o PostgreSQL cita
    o NOME da restrição, o SQLite cita as COLUNAS. Reconhecer só um dos dois
    faz a defesa existir num ambiente e não no outro — e o ambiente onde ela
    faltaria é justamente o de produção ou o de teste, conforme o descuido.
    """
    texto = str(erro).lower()
    if "sync_unique_sequence_per_source" in texto:
        return True
    return "syncevent" in texto and "sequence" in texto
