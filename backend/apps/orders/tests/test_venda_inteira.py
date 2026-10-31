"""A venda inteira num envio só: pedido, itens, comandas e recebimentos.

Antes o PDV fazia uma chamada para criar o pedido, uma por item, uma para
anexar as comandas e uma por recebimento. Uma troca loja/nuvem no meio
deixava metade da venda em cada servidor. Agora é UM payload, numa transação:
entra inteiro ou não entra. Tudo tem o UUID que o PDV deu, então o reenvio
(rede caiu, desvio para a nuvem) devolve a mesma venda, sem duplicar nada.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.orders.command_item_launch import launch_item
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db
URL = "/api/v1/orders/submit/"


def _venda(restaurant, produto, dinheiro=None, *, valor="50.00", comandas=(), itens=2):
    corpo = {
        "id": str(uuid.uuid4()), "order_type": "counter", "restaurant": str(restaurant.pk),
        "items": [{"id": str(uuid.uuid4()), "product": str(produto.pk), "quantity": 1}
                  for _ in range(itens)],
        "commands": [str(c.pk) for c in comandas],
        "payments": [],
    }
    if dinheiro is not None:
        corpo["payments"] = [{"id": str(uuid.uuid4()), "payment_method": str(dinheiro.pk),
                              "amount": valor, "client_updated_at": "2026-10-10T12:00:00Z"}]
    return corpo


def test_pedido_itens_e_pagamento_num_envio_so(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro
):
    corpo = _venda(restaurant, produto, dinheiro)

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 201, resposta.content
    pedido = Order.all_objects.get(pk=corpo["id"])
    assert pedido.payment_status == "paid" and pedido.total == Decimal("50.00")
    assert {str(i) for i in OrderItem.all_objects.filter(order=pedido).values_list("id", flat=True)} == {
        i["id"] for i in corpo["items"]}
    assert str(Payment.all_objects.get(order=pedido).pk) == corpo["payments"][0]["id"]


def test_reenvio_devolve_a_mesma_venda_sem_duplicar(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro
):
    corpo = _venda(restaurant, produto, dinheiro)
    api_client.post(URL, corpo, format="json")

    reenvio = api_client.post(URL, corpo, format="json")

    assert reenvio.status_code in (200, 201), reenvio.content
    assert reenvio.json()["order"]["id"] == corpo["id"]
    assert OrderItem.all_objects.filter(order_id=corpo["id"]).count() == 2
    assert Payment.all_objects.filter(order_id=corpo["id"]).count() == 1


def test_falha_no_meio_nao_deixa_nada_para_tras(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro
):
    """Forma de pagamento inválida: nem o pedido nem os itens podem ficar."""
    corpo = _venda(restaurant, produto, dinheiro)
    corpo["payments"][0]["payment_method"] = str(uuid.uuid4())

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 400, resposta.content
    assert not Order.all_objects.filter(pk=corpo["id"]).exists()
    assert not OrderItem.all_objects.filter(pk__in=[i["id"] for i in corpo["items"]]).exists()


def test_simular_devolve_o_total_e_nao_grava_nada(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto
):
    corpo = {**_venda(restaurant, produto), "simular": True}

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 200, resposta.content
    assert Decimal(resposta.json()["order"]["total"]) == Decimal("50.00")
    assert not Order.all_objects.filter(pk=corpo["id"]).exists()


def test_comanda_e_pagamento_juntos_e_o_item_tem_uuid_calculado(
    api_client, contexto_tenant, sem_caixa_obrigatorio, account, restaurant, branch, produto,
    dinheiro, manager_user
):
    """O item que vem da comanda tem UUID calculado (pedido + anotação): o mesmo
    envio feito na loja e na nuvem gera o MESMO item, e a sincronização junta."""
    from apps.orders.command_item_to_order import id_do_item_da_anotacao

    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     number=77)
    anotacao = launch_item(command=comanda, product=produto, user=manager_user)
    corpo = _venda(restaurant, produto, dinheiro, valor="25.00", comandas=[comanda], itens=0)

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 201, resposta.content
    item = OrderItem.all_objects.get(command_item=anotacao)
    assert item.pk == id_do_item_da_anotacao(corpo["id"], anotacao.pk)
    assert Order.all_objects.get(pk=corpo["id"]).payment_status == "paid"
    # Reenviar (já paga, anotação concluída) não é "nada a cobrar": é a mesma venda.
    assert api_client.post(URL, corpo, format="json").status_code in (200, 201)


def test_pagar_depois_cria_o_pedido_e_o_pagamento_vem_noutro_envio(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro
):
    sem_pagamento = _venda(restaurant, produto)
    assert api_client.post(URL, sem_pagamento, format="json").status_code == 201
    assert Order.all_objects.get(pk=sem_pagamento["id"]).payment_status == "pending"

    com_pagamento = {**_venda(restaurant, produto, dinheiro), "id": sem_pagamento["id"],
                     "items": sem_pagamento["items"]}
    resposta = api_client.post(URL, com_pagamento, format="json")

    assert resposta.status_code in (200, 201), resposta.content
    assert Order.all_objects.get(pk=sem_pagamento["id"]).payment_status == "paid"
    assert OrderItem.all_objects.filter(order_id=sem_pagamento["id"]).count() == 2


def test_admin_web_pode_materializar_na_unidade_escolhida(admin_client, account):
    """O payload do web decide a unidade; antes o backend ignorava esse campo."""
    from apps.restaurants.models import Restaurant

    with tenant_context(account):
        outra = Restaurant.objects.create(
            account=account,
            legal_name="Outra unidade",
            trade_name="Outra unidade",
        )
    order_id = str(uuid.uuid4())

    response = admin_client.post(
        URL,
        {
            "id": order_id,
            "restaurant": str(outra.pk),
            "order_type": "counter",
            "items": [],
            "commands": [],
            "payments": [],
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert Order.all_objects.get(pk=order_id).restaurant_id == outra.pk
