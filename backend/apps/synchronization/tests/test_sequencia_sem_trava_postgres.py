"""Reservar o número do evento não pode travar as outras gravações (PostgreSQL).

O número vinha de um `UPDATE` na linha do nó (`sequence_counter + 1`), e a
trava dessa linha durava até o fim da transação. TODA gravação que sincroniza
passava por ela: lançar na comanda, pesar, abrir o caixa, receber. Com três
caixas e cinco garçons, as transações se esperavam em círculo (o contador de
um lado, a linha do restaurante e da comanda do outro) e o PostgreSQL
derrubava uma delas — 500 no "abrir caixa", achado pela simulação do dia a
dia (`loadtest/dia_a_dia`) no par real.

Agora o número vem de uma SEQUENCE do banco, que não trava linha nenhuma.
"""
import threading

import pytest
from django.db import connection, connections, transaction

from apps.synchronization.models import SyncNode

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(connection.vendor != "postgresql",
                       reason="a trava de linha só existe no PostgreSQL"),
]


def test_transacao_aberta_com_numero_reservado_nao_trava_a_proxima(como_loja, no_loja):
    reservou, pode_terminar = threading.Event(), threading.Event()
    resultado = {}

    def primeira():
        try:
            with transaction.atomic():
                resultado["a"] = SyncNode.objects.get(pk=no_loja.pk).next_sequence()
                reservou.set()
                pode_terminar.wait(10)
        finally:
            connections.close_all()

    fio = threading.Thread(target=primeira)
    fio.start()
    assert reservou.wait(10)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '2s'")
            resultado["b"] = SyncNode.objects.get(pk=no_loja.pk).next_sequence()
    finally:
        pode_terminar.set()
        fio.join(10)

    assert resultado["b"] != resultado["a"]


def test_numeros_continuam_unicos_e_crescentes(como_loja, no_loja):
    no = SyncNode.objects.get(pk=no_loja.pk)
    numeros = [no.next_sequence() for _ in range(5)]

    assert numeros == sorted(numeros)
    assert len(set(numeros)) == 5
