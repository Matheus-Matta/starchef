"""O servidor ACEITA o total que o PDV calcula sozinho.

O PDV passou a montar a conta da tela de pagamento sem perguntar ao servidor
(`fechamento_local.dart`). O servidor continua sendo a autoridade: a conclusão
leva o total mostrado (`expected_total`) e ele recusa com 409 se não bater.

Aqui vão ao `/orders/submit/` as MESMAS vendas que o teste do PDV monta
(`pdv_desktop/test/fixtures/vendas_do_pdv.json`), cada uma com o total que o
PDV chegou. Um centavo de diferença seria uma venda recusada no caixa com
"total mudou" — foi o que apareceu no buffet de R$ 49,90 o quilo com 750 g.
"""
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings

from apps.menu.models import Product
from apps.orders.command_item_launch import launch_item
from apps.orders.models import Order
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db

TABELA = json.loads(
    (Path(settings.BASE_DIR).parent / "pdv_desktop" / "test" / "fixtures" / "vendas_do_pdv.json")
    .read_text(encoding="utf-8"))
URL = "/api/v1/orders/submit/"


def _produtos(account, restaurant, branch):
    return {
        ref: Product.objects.create(
            account=account, restaurant=restaurant, branch=branch, name=ref,
            internal_code=f"V{uuid.uuid4().hex[:6]}", sale_price=Decimal(dados["preco"]),
            **({"pricing_unit": Product.PRICING_KG} if dados.get("por_quilo") else {}),
        )
        for ref, dados in TABELA["produtos"].items()
    }


def _linha(linha, produtos):
    produto = produtos[linha["produto"]]
    corpo = {"id": str(uuid.uuid4()), "product": str(produto.pk), "variations": [], "addons": [],
             "customer_note": ""}
    if linha.get("peso_kg"):
        return {**corpo, "weight_kg": linha["peso_kg"]}
    return {**corpo, "quantity": linha["quantidade"], "expected_unit_price": str(produto.sale_price)}


@pytest.mark.parametrize("venda", TABELA["vendas"], ids=[v["nome"] for v in TABELA["vendas"]])
def test_o_servidor_aceita_o_total_do_pdv(venda, api_client, contexto_tenant, sem_caixa_obrigatorio,
                                          account, restaurant, branch, manager_user, dinheiro):
    restaurant.default_service_fee_percent = Decimal(venda["taxa"])
    restaurant.save(update_fields=["default_service_fee_percent"])
    produtos = _produtos(account, restaurant, branch)
    comandas, vistas = [], []
    for comanda in venda.get("comandas", []):
        cartao = Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                        number=comanda["numero"])
        comandas.append(str(cartao.pk))
        vistas += [str(launch_item(command=cartao, product=produtos[a["produto"]], user=manager_user).pk)
                   for a in comanda["anotacoes"]]
    ajustes = venda["ajustes"]
    corpo = {
        "id": str(uuid.uuid4()), "order_type": "command" if comandas else "counter",
        "restaurant": str(restaurant.pk),
        "items": [_linha(linha, produtos) for linha in venda["linhas"]],
        "commands": comandas, **({"command_items": vistas} if comandas else {}),
        "kitchen": {"client_batch_serial": "PDV-1"},
        "close": {"service_fee_enabled": ajustes.get("service_fee_enabled", True),
                  "discount": ajustes.get("discount", "0.00"),
                  "fiscal_customer_cpf": ajustes.get("fiscal_customer_cpf", ""),
                  "fiscal_customer_cnpj": "", "coupon_code": ""},
        "payments": [{"id": str(uuid.uuid4()), "payment_method": str(dinheiro.pk),
                      "amount": venda["total"], "client_updated_at": "2026-10-19T12:00:00Z"}],
        "expected_total": venda["total"],
    }

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 201, resposta.content
    pedido = Order.all_objects.get(pk=corpo["id"])
    assert pedido.total == Decimal(venda["total"])
    assert pedido.payment_status == Order.PAYMENT_PAID
