"""A venda inteira: fechamento, cozinha, comanda vista e reenvio a pedido pago.

Continuação de `test_venda_inteira.py` (mesmo cenário e ajudantes).
"""
import uuid
from decimal import Decimal

import pytest

from apps.orders.command_item_launch import launch_item
from apps.orders.models import Order, OrderItem
from apps.orders.tests.test_venda_inteira import URL, _venda
from apps.payments.models import Payment
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def test_fechamento_com_taxa_e_cpf_vai_no_mesmo_envio(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro
):
    """Taxa de serviço, CPF e cupom eram um `/close/` à parte antes de pagar:
    mais uma chamada que podia cair do outro lado. Agora vão no mesmo corpo,
    e o simular já devolve o total com a taxa para a tela de pagamento."""
    restaurant.default_service_fee_percent = Decimal("10.00")
    restaurant.save(update_fields=["default_service_fee_percent"])
    fechamento = {"service_fee_enabled": True, "fiscal_customer_cpf": "52998224725"}
    simulado = api_client.post(URL, {**_venda(restaurant, produto), "close": fechamento,
                                     "simular": True}, format="json").json()["order"]
    assert Decimal(simulado["total"]) == Decimal("55.00")

    corpo = {**_venda(restaurant, produto, dinheiro, valor=simulado["total"]), "close": fechamento}
    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 201, resposta.content
    pedido = Order.all_objects.get(pk=corpo["id"])
    assert pedido.payment_status == "paid" and pedido.total == Decimal("55.00")
    assert pedido.fiscal_customer_cpf.endswith("52998224725")


def test_envio_a_cozinha_vai_no_mesmo_envio(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto
):
    """F9 abria o pedido e depois chamava `send-to-kitchen`: duas chamadas."""
    corpo = {**_venda(restaurant, produto), "kitchen": {"client_batch_serial": "LOTE-1"}}

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 201, resposta.content
    assert not OrderItem.all_objects.filter(order_id=corpo["id"], status="pending").exists()
    # Reenviado, não manda de novo para a produção.
    assert api_client.post(URL, corpo, format="json").status_code in (200, 201)


def test_so_as_anotacoes_que_o_caixa_viu_entram_na_conta(
    api_client, contexto_tenant, sem_caixa_obrigatorio, account, restaurant, branch, produto,
    dinheiro, manager_user
):
    """Achado no par Docker: o caixa abriu o pagamento da comanda (simulou R$ 25)
    e, enquanto o cliente pagava, o garçom lançou mais um item. A conclusão
    puxava TUDO o que estava pendente: a conta fechava com R$ 50 e R$ 25 pagos.
    Entra só o que o caixa viu; o lançado depois fica para a próxima conta."""
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     number=88)
    vista = launch_item(command=comanda, product=produto, user=manager_user)
    nova = launch_item(command=comanda, product=produto, user=manager_user)  # depois de abrir
    corpo = {**_venda(restaurant, produto, dinheiro, valor="25.00", comandas=[comanda], itens=0),
             "command_items": [str(vista.pk)]}

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 201, resposta.content
    pedido = Order.all_objects.get(pk=corpo["id"])
    assert pedido.payment_status == "paid" and pedido.total == Decimal("25.00")
    assert not OrderItem.all_objects.filter(command_item=nova).exists()


def test_reenvio_a_pedido_ja_pago_nao_e_erro_e_vai_ao_historico(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro
):
    """Achado no par Docker: a venda chegou à outra ponta depois de o PEDIDO pago
    ter chegado pela sincronização, mas antes do recebimento dele. O reenvio
    trazia um UUID de recebimento que ali ainda não existia, e o servidor
    respondia 400 "O pedido já foi pago." — numa venda que deu certo."""
    from apps.synchronization.models import SyncDiscard

    corpo = _venda(restaurant, produto, dinheiro)
    api_client.post(URL, corpo, format="json")
    reenvio = {**corpo, "payments": [{**corpo["payments"][0], "id": str(uuid.uuid4())}]}

    resposta = api_client.post(URL, reenvio, format="json")

    assert resposta.status_code in (200, 201), resposta.content
    assert Payment.all_objects.filter(order_id=corpo["id"]).count() == 1
    assert SyncDiscard.objects.filter(entity_id=reenvio["payments"][0]["id"]).exists()


def test_total_diferente_do_que_o_caixa_mostrou_e_recusado_sem_gravar(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro
):
    """Achado no par Docker: entre simular (R$ 566,90) e concluir, parte da
    comanda foi cobrada em outra conta; o total real caiu para R$ 182,40 e o
    caixa recebeu pelo valor velho. Com `expected_total`, o servidor recusa
    (409) sem gravar nada, e o PDV mostra o valor novo antes de receber."""
    corpo = {**_venda(restaurant, produto, dinheiro), "expected_total": "75.00"}

    resposta = api_client.post(URL, corpo, format="json")

    assert resposta.status_code == 409, resposta.content
    assert "50,00" in str(resposta.content.decode()) or "50.00" in resposta.content.decode()
    assert not Order.all_objects.filter(pk=corpo["id"]).exists()
    # O total certo passa.
    ok = api_client.post(URL, {**corpo, "expected_total": "50.00"}, format="json")
    assert ok.status_code == 201, ok.content
