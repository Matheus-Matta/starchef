"""O contador do nó atrás dos eventos se realinha em vez de travar a loja."""
import pytest

from apps.synchronization.models import SyncEvent
from apps.synchronization.tests.test_outbox import _restaurante

pytestmark = pytest.mark.django_db


def test_contador_atrasado_se_realinha_em_vez_de_travar_a_loja(como_nuvem, conta):
    """O banco restaurado de um backup mais velho que os eventos.

    O contador do no e os eventos sao duas fontes para o MESMO numero, e saem
    de sincronia sem ninguem reclamar: restauracao, no recriado, importacao
    com sequencia explicita.

    A partir dai TODA escrita sincronizada do no colide — abrir um pedido,
    lancar um item, receber um pagamento. O operador via "ja existe um
    registro com estes dados" em cima de um gesto que nao tinha nada de
    duplicado, nada indicava onde procurar, e o erro NAO passava sozinho.
    """
    _restaurante(conta, "Antes da restauracao")
    evento = SyncEvent.objects.get(entity_type="restaurant")

    from django.db import connection

    from apps.synchronization.services import sequencia_pg

    # O backup volta com o contador atras dos eventos que ja existem. No
    # PostgreSQL o contador e a sequence (`sequencia_pg`); no SQLite, a linha.
    no = como_nuvem
    if sequencia_pg.disponivel():
        with connection.cursor() as cursor:
            cursor.execute("SELECT setval(%s, %s)", [sequencia_pg.NOME, evento.sequence - 1])
    else:
        no.sequence_counter = evento.sequence - 1
        no.save(update_fields=["sequence_counter"])

    # A proxima venda nao pode encontrar a loja travada.
    _restaurante(conta, "Depois da restauracao")

    novo = SyncEvent.objects.get(payload__fields__trade_name="Depois da restauracao")
    assert novo.sequence > evento.sequence

    # E o conserto e DEFINITIVO: o contador ficou acima de tudo que existe.
    if sequencia_pg.disponivel():
        assert sequencia_pg.atual() >= novo.sequence
    else:
        no.refresh_from_db(fields=["sequence_counter"])
        assert no.sequence_counter >= novo.sequence
