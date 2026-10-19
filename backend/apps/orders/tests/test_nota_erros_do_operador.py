"""A venda com NFC-e diante dos erros de quem opera o caixa.

Cada teste é um gesto que acontece de verdade no balcão: o Concluir clicado
duas vezes, a nota pedida de novo, a venda cancelada com o PDV ainda pedindo a
nota, o cliente pagando a menos, o CPF digitado errado. A nota sai em segundo
plano (`invoices/signals.py`); aqui a fila roda na hora (Celery em modo eager)
e o `on_commit` é executado, como no servidor.
"""
from decimal import Decimal

import pytest

from apps.orders.command_item_launch import launch_item
from apps.orders.models import Order
from apps.orders.services import cancel_order
from apps.orders.tests.nota_da_venda import notas_do, venda
from apps.payments.models import Payment
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def _numero_usado(config):
    config.refresh_from_db()
    return config.next_number - 1


def test_concluir_clicado_duas_vezes_faz_uma_venda_e_uma_nota(caixa, restaurant, produto, dinheiro):
    """A tela demorou e o caixa clicou de novo: o segundo envio é a MESMA venda.

    Duas notas para uma venda gastariam dois números da série e a segunda teria
    de ser cancelada na SEFAZ."""
    corpo = venda(restaurant, produto, dinheiro)

    primeira = caixa.concluir(corpo)
    segunda = caixa.concluir(corpo)

    assert primeira.status_code == 201, primeira.content
    assert segunda.status_code in (200, 201), segunda.content
    assert Payment.all_objects.filter(order_id=corpo["id"]).count() == 1
    assert notas_do(corpo["id"]).count() == 1
    assert _numero_usado(caixa.config) == 1


def test_pdv_que_pede_a_nota_duas_vezes_recebe_a_mesma_sem_gastar_numero(
    caixa, restaurant, produto, dinheiro
):
    """O PDV repete o pedido da nota depois de 20 s sem resposta. Antes a
    segunda vinha 400 "Pedido já possui nota fiscal emitida" e o DANFE não saía."""
    corpo = venda(restaurant, produto, dinheiro)
    caixa.concluir(corpo)

    respostas = [caixa.pedir_nota(corpo["id"]) for _ in range(2)]

    assert [r.status_code for r in respostas] == [200, 200], [r.content for r in respostas]
    assert respostas[0].data["id"] == respostas[1].data["id"]
    assert respostas[0].data["printable"] is True
    assert _numero_usado(caixa.config) == 1


def test_venda_cancelada_continua_sem_nota_mesmo_com_o_pdv_pedindo(
    caixa, restaurant, produto, dinheiro, manager_user
):
    """A resposta "a nota que já existe" não pode esconder recusa de verdade:
    pedido cancelado não ganha nota nova só porque o PDV insistiu."""
    corpo = venda(restaurant, produto, dinheiro)
    caixa.concluir(corpo)
    cancel_order(Order.all_objects.get(pk=corpo["id"]), manager_user,
                 "Cliente desistiu da compra no balcao")

    resposta = caixa.pedir_nota(corpo["id"])

    assert resposta.status_code == 400, resposta.content
    assert "cancelad" in resposta.content.decode().lower()


def test_cliente_que_paga_a_menos_nao_gera_nota(caixa, restaurant, produto, dinheiro):
    """O caixa digitou 10 numa conta de 25. A venda fica em aberto, e nota de
    venda que não foi paga seria documento fiscal de dinheiro que não entrou."""
    corpo = venda(restaurant, produto, dinheiro, valor="10.00")

    resposta = caixa.concluir(corpo)

    assert resposta.status_code == 201, resposta.content
    assert Order.all_objects.get(pk=corpo["id"]).payment_status == Order.PAYMENT_PARTIAL
    assert not notas_do(corpo["id"]).exists()


def test_cpf_digitado_errado_trava_a_venda_antes_de_cobrar(caixa, restaurant, produto, dinheiro):
    """O CPF errado é recusado no fechamento: nada é gravado e nenhuma nota
    é pedida — o caixa corrige e conclui de novo com o mesmo envio."""
    corpo = venda(restaurant, produto, dinheiro, close={"fiscal_customer_cpf": "11111111111"})

    resposta = caixa.concluir(corpo)

    assert resposta.status_code == 400, resposta.content
    assert "CPF" in resposta.content.decode()
    assert not Order.all_objects.filter(pk=corpo["id"]).exists()
    assert not notas_do(corpo["id"]).exists()


def test_comanda_paga_com_troco_sai_livre_e_com_uma_nota(
    caixa, account, restaurant, branch, produto, dinheiro, manager_user
):
    """Cliente deu R$ 50 numa comanda de R$ 25: troco de R$ 25, comanda livre
    para o próximo, uma nota só."""
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     number=55)
    launch_item(command=comanda, product=produto, user=manager_user)
    corpo = venda(restaurant, produto, dinheiro, valor="50.00", itens=0, comandas=[comanda])

    resposta = caixa.concluir(corpo)

    assert resposta.status_code == 201, resposta.content
    assert Order.all_objects.get(pk=corpo["id"]).payment_status == Order.PAYMENT_PAID
    assert Payment.all_objects.get(order_id=corpo["id"]).change_amount == Decimal("25.00")
    comanda.refresh_from_db()
    assert comanda.status == Command.STATUS_FREE
    assert notas_do(corpo["id"]).count() == 1
