"""A web não manda `Idempotency-Key` — e sem ela não havia transação.

O middleware de idempotência abre a transação quando a requisição traz a
chave, e o PDV desktop manda em toda escrita. A web não manda. Dois serviços
travam linha (`select_for_update`) sem abrir transação própria, e no servidor
de verdade (autocommit) isso é `TransactionManagementError`: 500 ao excluir item
da venda e ao aprovar o fechamento/sangria pela senha do caixa — na web.

A suíte nunca pegou porque cada teste roda dentro de uma transação.
`transaction=True` roda como produção.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, create_order
from apps.payments.models import CashRegister
from apps.payments.services import close_cash_register, open_cash_register

pytestmark = pytest.mark.django_db(transaction=True)


def test_excluir_item_da_venda_sem_chave_de_idempotencia(
    api_client, contexto_tenant, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio,
):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    item = add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)

    resposta = api_client.delete(f"/api/v1/orders/{pedido.pk}/items/{item.pk}/void/", {"reason": "Desistiu"}, format="json")

    assert resposta.status_code == 200, resposta.content
    with tenant_context(restaurant.account):
        assert OrderItem.objects.get(pk=item.pk).status == OrderItem.STATUS_CANCELLED


def test_aprovar_fechamento_pela_senha_sem_chave_de_idempotencia(api_client, restaurant, branch, manager_user):
    restaurant.set_cash_action_password("4321")
    restaurant.cash_closing_tolerance = Decimal("0.00")
    restaurant.save()
    with tenant_context(restaurant.account):
        sessao = open_cash_register(restaurant=restaurant, branch=branch, user=manager_user, opening_amount=Decimal("100"))
        close_cash_register(cash_register=sessao, user=manager_user, actual_amount=Decimal("90"))

    resposta = api_client.post(
        f"/api/v1/cash-register/{sessao.pk}/approve/", {"reason": "Conferido", "cash_password": "4321"}, format="json"
    )

    assert resposta.status_code == 200, resposta.content
    with tenant_context(restaurant.account):
        assert CashRegister.objects.get(pk=sessao.pk).status != CashRegister.STATUS_PENDING_APPROVAL
