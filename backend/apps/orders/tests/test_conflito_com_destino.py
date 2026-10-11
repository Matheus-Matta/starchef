"""A recusa diz ONDE está o que o caixa procura — para o PDV ir até lá.

"A comanda 15 já está na conta #42" e "nada a cobrar" deixavam o caixa
procurando a conta na lista. Com o código e o pedido na resposta, o PDV abre a
conta certa em vez de mostrar um erro.
"""
import uuid
from decimal import Decimal

import pytest

from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_item_launch import launch_item
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def comanda(account, restaurant, branch, produto, manager_user):
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     number=15)
    launch_item(command=comanda, product=produto, user=manager_user)
    return comanda


def _conta(restaurant, branch, manager_user):
    return create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND,
                        user=manager_user)


def _erro(resposta):
    return resposta.json()["error"]


def test_comanda_em_outra_conta_aberta_diz_qual(
    api_client, contexto_tenant, restaurant, branch, comanda, manager_user
):
    aberta = _conta(restaurant, branch, manager_user)
    attach_commands_to_order(order=aberta, command_ids=[comanda.pk], user=manager_user)
    nova = _conta(restaurant, branch, manager_user)

    resposta = api_client.post(f"/api/v1/orders/{nova.pk}/attach-commands/",
                               {"commands": [str(comanda.pk)]}, format="json")

    assert resposta.status_code == 409
    assert _erro(resposta)["code"] == "comanda_em_outra_conta"
    assert _erro(resposta)["order_id"] == str(aberta.pk)


def test_comanda_ja_paga_diz_em_qual_pedido(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, branch, comanda, dinheiro,
    manager_user
):
    paga = _conta(restaurant, branch, manager_user)
    attach_commands_to_order(order=paga, command_ids=[comanda.pk], user=manager_user)
    api_client.post(f"/api/v1/orders/{paga.pk}/pay/", {
        "payment_method": str(dinheiro.pk), "amount": "25.00"}, format="json")
    nova = _conta(restaurant, branch, manager_user)

    resposta = api_client.post(f"/api/v1/orders/{nova.pk}/attach-commands/",
                               {"commands": [str(comanda.pk)]}, format="json")

    assert resposta.status_code == 409
    assert _erro(resposta)["code"] == "comanda_ja_cobrada"
    assert _erro(resposta)["order_id"] == str(paga.pk)


def test_pagar_pedido_ja_pago_diz_qual_e_e_409(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, branch, comanda, dinheiro,
    manager_user
):
    paga = _conta(restaurant, branch, manager_user)
    attach_commands_to_order(order=paga, command_ids=[comanda.pk], user=manager_user)
    corpo = {"payment_method": str(dinheiro.pk), "amount": "25.00"}
    api_client.post(f"/api/v1/orders/{paga.pk}/pay/", corpo, format="json")

    resposta = api_client.post(f"/api/v1/orders/{paga.pk}/pay/", corpo, format="json")

    assert resposta.status_code == 409
    assert _erro(resposta)["code"] == "pedido_ja_pago"
    assert _erro(resposta)["order_id"] == str(paga.pk)


def test_total_mudou_diz_onde_foi_cobrado(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, branch, comanda, dinheiro,
    produto, manager_user
):
    """Simulou com a anotação; antes de concluir, outra conta a cobrou."""
    outra = _conta(restaurant, branch, manager_user)
    attach_commands_to_order(order=outra, command_ids=[comanda.pk], user=manager_user)
    api_client.post(f"/api/v1/orders/{outra.pk}/pay/", {  # outro caixa cobrou e fechou
        "payment_method": str(dinheiro.pk), "amount": "25.00"}, format="json")
    launch_item(command=comanda, product=produto, user=manager_user)  # o que sobrou para cobrar

    resposta = api_client.post("/api/v1/orders/submit/", {
        "id": str(uuid.uuid4()), "order_type": "command", "items": [],
        "commands": [str(comanda.pk)], "expected_total": "50.00",
        "payments": [{"id": str(uuid.uuid4()), "payment_method": str(dinheiro.pk),
                      "amount": "50.00"}],
    }, format="json")

    assert resposta.status_code == 409, resposta.content
    erro = _erro(resposta)
    assert erro["code"] == "total_mudou"
    assert Decimal(erro["expected_total"]) == Decimal("50.00")
    assert Decimal(erro["total"]) == Decimal("25.00")
    assert str(outra.pk) in [c["order_id"] for c in erro["cobradas_em"]]
