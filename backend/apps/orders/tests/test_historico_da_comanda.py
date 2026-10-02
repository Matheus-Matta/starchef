"""A linha do tempo de uma comanda: tudo o que aconteceu com o cartão.

A pergunta do balcão é "quem lançou isso, quando, e por que sumiu?". As
respostas já estavam gravadas, espalhadas: no item (lançado, produção,
cancelado, encerrado), no pedido que cobrou, no registro de mesa e na
auditoria (zeramento). A rota de histórico junta tudo, do mais novo para o
mais antigo, com autor, código do operador e motivo.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_item_void import void_command_item
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem, Order
from apps.orders.services import create_order
from apps.payments.models import PaymentMethod
from apps.payments.services import register_payment
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def ciclo(contexto_tenant, account, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio):
    """Um uso do cartão: dois lançamentos, um cancelado, o outro cobrado."""
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=31)
    pago = launch_item(
        command=comanda, product=produto, user=manager_user, quantity=1, metafields={"operator_code": "4821"}
    )
    cancelado = launch_item(command=comanda, product=produto, user=manager_user, quantity=2)
    CommandItem.objects.filter(pk=pago.pk).update(sent_to_kitchen_at=timezone.now())
    void_command_item(cancelado, user=manager_user, reason="Cliente desistiu")
    conta = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, user=manager_user)
    attach_commands_to_order(order=conta, command_ids=[comanda.pk], user=manager_user)
    conta.refresh_from_db()
    dinheiro = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Dinheiro", method_type=PaymentMethod.TYPE_CASH
    )
    register_payment(order=conta, user=manager_user, payment_method_id=dinheiro.pk, amount=conta.total)
    return comanda, conta


def _historico(cliente, comanda, **params):
    resposta = cliente.get(f"/api/v1/commands/{comanda.pk}/history/", params)
    assert resposta.status_code == 200, resposta.content
    return resposta.data


def test_conta_o_ciclo_inteiro_do_mais_novo_ao_mais_antigo(api_client, ciclo):
    comanda, conta = ciclo

    eventos = _historico(api_client, comanda)["results"]
    tipos = [e["kind"] for e in eventos]

    for esperado in ("launched", "sent_to_production", "voided", "charged"):
        assert esperado in tipos, tipos
    instantes = [e["at"] for e in eventos]
    assert instantes == sorted(instantes, reverse=True)

    cancelamento = next(e for e in eventos if e["kind"] == "voided")
    assert cancelamento["reason"] == "Cliente desistiu"
    assert cancelamento["user"]
    cobranca = next(e for e in eventos if e["kind"] == "charged")
    assert cobranca["order"]["sequence"] == conta.sequence
    lancamento_com_codigo = [e for e in eventos if e["kind"] == "launched" and e["operator_code"] == "4821"]
    assert len(lancamento_com_codigo) == 1
    assert lancamento_com_codigo[0]["item"]["product"]


def test_zeramento_aparece_com_motivo(api_client, ciclo, restaurant, branch, manager_user, produto):
    comanda, _conta = ciclo
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    api_client.post("/api/v1/commands/bulk-reset/", {"ids": [str(comanda.pk)], "reason": "Fim do dia"}, format="json")

    eventos = _historico(api_client, comanda)["results"]

    zeramento = next(e for e in eventos if e["kind"] == "reset")
    assert zeramento["reason"] == "Fim do dia"
    assert eventos[0]["kind"] in {"reset", "voided"}


def test_paginado(api_client, ciclo):
    comanda, _conta = ciclo

    primeira = _historico(api_client, comanda, page_size=2)
    segunda = _historico(api_client, comanda, page_size=2, page=2)

    assert len(primeira["results"]) == 2
    assert primeira["count"] >= 4
    assert primeira["next"]
    assert primeira["results"] != segunda["results"]


def test_comanda_de_outra_conta_nao_aparece(api_client):
    from apps.accounts.models import Account
    from apps.restaurants.models import Restaurant

    outra = Account.objects.create(name="Outra", slug="outra-conta-hist", status=Account.STATUS_ACTIVE, is_active=True)
    with tenant_context(outra):
        outro = Restaurant.objects.create(account=outra, legal_name="Outro", trade_name="Outro", cnpj="1" * 14)
        alheia = Command.objects.create(account=outra, restaurant=outro, number=1)

    assert api_client.get(f"/api/v1/commands/{alheia.pk}/history/").status_code == 404


def test_valor_do_item_vai_junto(api_client, ciclo):
    comanda, _conta = ciclo

    lancamentos = [e for e in _historico(api_client, comanda)["results"] if e["kind"] == "launched"]

    assert sorted(Decimal(e["item"]["total"]) for e in lancamentos) == [Decimal("25.00"), Decimal("50.00")]
