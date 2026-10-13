"""O recibo da venda sai com o TEXTO; o HTML só quando alguém o pede.

Gerar o HTML custava ~0,19 s numa venda de 50 itens, dentro da conclusão,
com o cliente esperando — e quem imprime não o usa: o PDV, o app do garçom e
o agente leem `payload.text_content` (o HTML é o último recurso, sem texto).
Ele só serve à pré-visualização, e é gerado quando ela é pedida.
"""
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.printers.models import Printer, PrintJob
from apps.printers.services import html_do_trabalho, register_print_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido(account, restaurant, branch, manager_user):
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Suco", internal_code="SUCO-HTML", sale_price=Decimal("8.00"))
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=2, user=manager_user)
    Printer.objects.create(account=account, restaurant=restaurant, branch=branch, name="Caixa",
                           driver_type=Printer.DRIVER_ESCPOS, connection_type=Printer.CONNECTION_NETWORK,
                           host="192.168.10.50", port=9100)
    return pedido


def test_recibo_nasce_com_texto_e_sem_html(pedido, manager_user):
    job = register_print_job(order=pedido, user=manager_user, job_type=PrintJob.TYPE_RECEIPT)

    assert job.payload["text_content"].strip()
    assert job.html_content == ""


def test_o_html_e_gerado_quando_pedido_e_fica_guardado(pedido, manager_user):
    job = register_print_job(order=pedido, user=manager_user, job_type=PrintJob.TYPE_RECEIPT)

    html = html_do_trabalho(job)

    assert "Suco" in html
    job.refresh_from_db()
    assert job.html_content == html
