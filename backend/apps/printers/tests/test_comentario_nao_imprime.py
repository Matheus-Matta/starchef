"""Comentário de template não sai no papel.

Produção, 19/11/2026: o recibo da web imprimia "{# Por peso, a quantidade
aparece uma vez só... #}" uma vez por item. O `{# #}` do Django só vale numa
linha; quebrado em duas, vira texto. Comentário longo usa `{% comment %}`.
"""
import re
from pathlib import Path

import pytest

PASTA = Path(__file__).resolve().parents[1] / "templates"
TEMPLATES = sorted(PASTA.rglob("*.html"))


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_nenhum_comentario_curto_atravessa_linha(template):
    texto = template.read_text(encoding="utf-8")
    quebrados = [linha for linha in texto.splitlines() if re.search(r"\{#(?!.*#\})", linha)]
    assert not quebrados, f"{template.name}: use {{% comment %}} — {quebrados}"


@pytest.mark.django_db
def test_recibo_nao_imprime_o_comentario(account, restaurant, branch, manager_user):
    from decimal import Decimal

    from apps.menu.models import Product
    from apps.orders.models import Order
    from apps.orders.services import add_order_item, create_order
    from apps.printers.models import Printer, PrintJob
    from apps.printers.services import html_do_trabalho, register_print_job

    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Buffet", internal_code="BUF-COMENT", sale_price=Decimal("9"))
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    Printer.objects.create(account=account, restaurant=restaurant, branch=branch, name="Caixa",
                           driver_type=Printer.DRIVER_ESCPOS, connection_type=Printer.CONNECTION_NETWORK,
                           host="192.168.10.50", port=9100)
    job = register_print_job(order=pedido, user=manager_user, job_type=PrintJob.TYPE_RECEIPT)

    html = html_do_trabalho(job)

    assert "Buffet" in html
    assert "{#" not in html and "Por peso" not in html
