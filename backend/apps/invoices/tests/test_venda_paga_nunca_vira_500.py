"""Venda paga e gravada nunca responde 500 por causa da nota.

Achado no PDV desktop depois da v3.1.10: o "Concluir" falhava na primeira vez
(HTTP 500) e passava na segunda. O aviso de "pedido quitado" roda DEPOIS do
commit, e o receptor da nota só tratava `kombu.OperationalError` ao enfileirar.
Com o Celery finalmente configurado no processo web, um erro do Redis de outro
tipo (`redis.ConnectionError`) escapava — a venda já estava gravada, a resposta
saía 500, e o segundo clique achava a venda pronta.
"""
from unittest import mock

import pytest
import redis

from apps.invoices.models import Invoice
from apps.invoices.tasks import emitir_nota_do_pedido_pago_task
from apps.invoices.tests import test_nota_em_segundo_plano as base
from apps.invoices.tests.test_auto_issue_on_payment import _pay
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db
ENFILEIRAR = base.ENFILEIRAR
# As mesmas fixtures do teste da nota em segundo plano.
cadastro_fiscal, dinheiro_do_caixa, pedido = base.cadastro_fiscal, base.dinheiro_do_caixa, base.pedido


def test_erro_do_redis_ao_enfileirar_emite_a_nota_na_hora_e_a_venda_conclui(
    pedido, dinheiro_do_caixa, cadastro_fiscal, manager_user, django_capture_on_commit_callbacks
):
    with mock.patch(ENFILEIRAR, side_effect=redis.exceptions.ConnectionError("conexão fechada")):
        with django_capture_on_commit_callbacks(execute=True):
            _pay(pedido, dinheiro_do_caixa, manager_user)

    assert Invoice.all_objects.filter(order=pedido, status=Invoice.STATUS_ISSUED).exists()


def test_falha_da_nota_depois_do_commit_nao_desfaz_a_resposta_da_venda(
    pedido, dinheiro_do_caixa, cadastro_fiscal, manager_user, django_capture_on_commit_callbacks
):
    """Fila e emissão na hora falhando: a venda está gravada e o caixa segue.
    A nota fica para a varredura de pagos sem nota (`emitir_pagos_sem_nota`)."""
    with mock.patch(ENFILEIRAR, side_effect=redis.exceptions.ConnectionError("fora")), \
         mock.patch("apps.invoices.services.issue_invoice_for_paid_order", side_effect=RuntimeError("SEFAZ")):
        with django_capture_on_commit_callbacks(execute=True):
            _pay(pedido, dinheiro_do_caixa, manager_user)

    assert Payment.all_objects.filter(order=pedido).exists()


def test_a_tarefa_da_nota_nao_guarda_resultado():
    """Ninguém lê o resultado. Guardar fazia o processo web abrir uma conexão
    a mais com o Redis só para ouvir a resposta — e era ela que falhava."""
    assert emitir_nota_do_pedido_pago_task.ignore_result is True
