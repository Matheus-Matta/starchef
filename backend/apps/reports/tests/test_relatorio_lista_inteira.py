"""A tabela do relatório recebe a lista INTEIRA, até 1.000 linhas.

A tabela ordena e pagina no navegador. O servidor cortava cada lista em 100
(e o caixa em 200), e a tela pedia 10: ordenar "do mais vendido para o menos"
escolhia entre as linhas que vieram, não entre todos os produtos. O corte que
sobra é avisado pela tabela (`pagination.<lista>.count`).
"""
import uuid
from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.menu.models import Product
from apps.orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db


def test_relatorio_de_produtos_devolve_mais_de_cem_linhas(api_client, account, restaurant, branch,
                                                          manager_user):
    tenant = {"account": account, "restaurant": restaurant, "branch": branch}
    pedido = Order.objects.create(**tenant, sequence=1, order_type=Order.TYPE_COUNTER,
                                  status=Order.STATUS_PAID, payment_status=Order.PAYMENT_PAID,
                                  total=Decimal("0.00"))
    for n in range(120):
        produto = Product.objects.create(**tenant, name=f"Produto {n:03d}",
                                         internal_code=f"L{uuid.uuid4().hex[:6]}",
                                         sale_price=Decimal("10.00"))
        OrderItem.objects.create(**tenant, order=pedido, product=produto, quantity=n + 1,
                                 unit_price="10.00", total_price=Decimal("10.00") * (n + 1))
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    dados = api_client.get("/api/v1/reports/products/", {"page_size": 1000}).data

    assert len(dados["by_product"]) == 120
    assert dados["pagination"]["by_product"]["count"] == 120


def test_pedir_mais_que_o_teto_nao_derruba_o_servidor(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    resposta = api_client.get("/api/v1/reports/payments/", {"page_size": 999999})

    assert resposta.status_code == 200
    assert resposta.data["pagination"]["by_payment_method"]["page_size"] == 1000
