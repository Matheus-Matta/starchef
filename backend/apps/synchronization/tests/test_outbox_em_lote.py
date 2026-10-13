"""A captura da sincronização numa venda, em lote — mesmos eventos, poucas idas.

Medido no alvo de carga com loja matriculada: cada registro salvo gerava seu
evento na hora (relê o registro, acha os destinos, reserva a sequência,
grava), e uma venda de 10 itens fazia 942 consultas — ~10 s na nuvem, a ~6 ms
cada. Em lote, a venda grava os MESMOS eventos, de uma vez, ainda dentro da
transação: o evento continua nascendo junto com o dado, ou não nasce.
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.restaurants.models import Restaurant
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import outbox_lote

pytestmark = pytest.mark.django_db


def _gravar(conta):
    a = Restaurant.objects.create(account=conta, legal_name="A LTDA", trade_name="A")
    b = Restaurant.objects.create(account=conta, legal_name="B LTDA", trade_name="B")
    a.trade_name = "A editada"
    a.save(update_fields=["trade_name"])
    a.trade_name = "A final"
    a.save(update_fields=["trade_name"])
    return a, b


def _eventos():
    return list(SyncEvent.objects.order_by("sequence").values_list(
        "entity_type", "entity_id", "operation", "payload"))


def test_em_lote_grava_um_evento_por_registro_com_o_estado_final(como_nuvem, conta):
    with outbox_lote.em_lote():
        a, b = _gravar(conta)
        assert SyncEvent.objects.count() == 0  # nada antes do fim do lote

    eventos = _eventos()
    restaurantes = [e for e in eventos if e[0] == "restaurant"]
    assert [e[1] for e in restaurantes] == [str(a.pk), str(b.pk)]  # ordem da captura
    assert restaurantes[0][3]["fields"]["trade_name"] == "A final"
    assert restaurantes[0][2] == "CREATE"  # criado e editado na venda = criado


def test_lote_e_o_caminho_normal_produzem_os_mesmos_eventos(como_nuvem, conta):
    """Os mesmos registros viram evento — no lote, um por registro."""
    _gravar(conta)
    normal = _eventos()
    SyncEvent.objects.all().delete()

    with outbox_lote.em_lote():
        _gravar(conta)
    em_lote = _eventos()

    def por_tipo(eventos):
        tipos = {}
        for tipo, entidade, *_ in eventos:
            tipos.setdefault(tipo, set()).add(entidade)
        return {tipo: len(ids) for tipo, ids in tipos.items()}

    assert por_tipo(em_lote) == por_tipo(normal)
    assert len({(e[0], e[1]) for e in em_lote}) == len(em_lote)  # um por registro


def test_em_lote_faz_bem_menos_consultas(como_nuvem, conta):
    with CaptureQueriesContext(connection) as normal:
        _gravar(conta)
    with CaptureQueriesContext(connection) as lote, outbox_lote.em_lote():
        _gravar(conta)
    assert len(lote.captured_queries) < len(normal.captured_queries) * 0.7


def test_descartando_nao_grava_evento_nenhum(como_nuvem, conta):
    with outbox_lote.descartando():
        _gravar(conta)
    assert SyncEvent.objects.count() == 0


def test_erro_dentro_do_lote_nao_grava_eventos(como_nuvem, conta):
    with pytest.raises(RuntimeError), outbox_lote.em_lote():
        _gravar(conta)
        raise RuntimeError("venda recusada")
    assert SyncEvent.objects.count() == 0
