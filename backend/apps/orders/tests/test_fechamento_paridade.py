"""O servidor e o PDV fazem a MESMA conta do fechamento.

O PDV passou a calcular taxa, desconto e total sozinho
(`pdv_desktop/lib/features/home/data/fechamento_local.dart`), sem simular a
venda inteira a cada toque. O servidor continua a autoridade: confere o total
mostrado na conclusão (`expected_total`) e recusa com 409 se não bater.

Para isso não virar recusa toda hora, as duas contas têm de ser iguais. A
tabela de casos é UMA, lida por este teste e pelo do PDV
(`fechamento_local_test.dart`): mudou o arredondamento de um lado, o teste do
outro quebra.
"""
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings

from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, close_order, create_order

pytestmark = pytest.mark.django_db

TABELA = Path(settings.BASE_DIR).parent / "pdv_desktop" / "test" / "fixtures" / "fechamento_paridade.json"
CASOS = json.loads(TABELA.read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("caso", CASOS, ids=[caso["nome"] for caso in CASOS])
def test_o_servidor_fecha_igual_ao_pdv(caso, contexto_tenant, account, restaurant, branch,
                                       manager_user):
    restaurant.default_service_fee_percent = Decimal(caso["percentual"])
    restaurant.save(update_fields=["default_service_fee_percent"])
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Conta", internal_code=f"F{uuid.uuid4().hex[:6]}",
                                     sale_price=Decimal(caso["subtotal"]))
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    pedido.refresh_from_db()

    fechado = close_order(pedido, manager_user, discount=caso["desconto"],
                          service_fee_enabled=caso["taxa_ligada"])

    assert fechado.subtotal == Decimal(caso["subtotal"])
    assert fechado.service_fee == Decimal(caso["taxa"])
    assert fechado.total == Decimal(caso["total"])
