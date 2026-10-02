"""Dois terminais fazendo coisas em conflito no MESMO instante, no Postgres.

No SQLite tudo é serializado e estes testes passariam pelo motivo errado; por
isso só rodam no Postgres (`--ds=config.settings.test_postgres`). Cada cenário
repete algumas vezes para a colisão acontecer de verdade.
"""
import threading
from functools import partial
import uuid
from decimal import Decimal

import pytest
from django.db import connection

from apps.core.tenant import tenant_context
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem, Order, OrderItem
from apps.orders.services import add_order_item, create_order
from apps.payments.models import Payment, PaymentMethod
from apps.restaurants.models import Command

pytestmark = [pytest.mark.django_db(transaction=True)]
RODADAS = 4


@pytest.fixture(autouse=True)
def _so_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("A corrida só é real no Postgres.")


def _ao_mesmo_tempo(*chamadas):
    """Dispara as chamadas juntas e devolve as respostas na mesma ordem."""
    largada = threading.Barrier(len(chamadas))
    respostas = [None] * len(chamadas)

    def rodar(i, chamada):
        from django.db import connections

        largada.wait()
        try:
            respostas[i] = chamada()
        finally:
            connections.close_all()

    linhas = [threading.Thread(target=rodar, args=(i, c)) for i, c in enumerate(chamadas)]
    [t.start() for t in linhas]
    [t.join() for t in linhas]
    return respostas


def _cliente(usuario):
    from conftest import _authenticated_client

    return _authenticated_client(usuario)


def _comanda(restaurant, branch, numero, produto, usuario, itens=2):
    with tenant_context(restaurant.account):
        cartao = Command.objects.create(account=restaurant.account, restaurant=restaurant, branch=branch, number=numero)
        for _ in range(itens):
            launch_item(command=cartao, product=produto, user=usuario, quantity=1)
    return cartao


def test_dois_terminais_zerando_a_mesma_comanda(restaurant, branch, manager_user, produto):
    for rodada in range(RODADAS):
        cartao = _comanda(restaurant, branch, 700 + rodada, produto, manager_user)
        corpo = {"ids": [str(cartao.pk)], "reason": "Fim do dia"}
        a, b = _cliente(manager_user), _cliente(manager_user)

        r1, r2 = _ao_mesmo_tempo(
            partial(a.post, "/api/v1/commands/bulk-reset/", corpo, format="json"),
            partial(b.post, "/api/v1/commands/bulk-reset/", corpo, format="json"),
        )

        assert {r1.status_code, r2.status_code} == {200}, (r1.content, r2.content)
        retirados = sum(z["items_removed"] for r in (r1, r2) for z in r.data["reset"])
        assert retirados == 2, (r1.data, r2.data)
        with tenant_context(restaurant.account):
            from apps.core.models import AuditLog

            itens = list(CommandItem.objects.filter(command=cartao))
            assert all(i.status == CommandItem.STATUS_CANCELLED for i in itens)
            canceladas = AuditLog.objects.filter(entity="CommandItem", object_id__in=[str(i.pk) for i in itens],
                                                 metadata__event="command_item_voided").count()
            assert canceladas == 2  # cada item uma vez só


def test_zerar_e_anexar_a_conta_ao_mesmo_tempo(restaurant, branch, manager_user, produto):
    """Nenhum item pode terminar cancelado E dentro de uma conta aberta."""
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    for rodada in range(RODADAS):
        cartao = _comanda(restaurant, branch, 720 + rodada, produto, manager_user)
        with tenant_context(restaurant.account):
            conta = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, user=manager_user)
        a, b = _cliente(manager_user), _cliente(manager_user)

        _ao_mesmo_tempo(
            partial(a.post, "/api/v1/commands/bulk-reset/", {"ids": [str(cartao.pk)], "reason": "x"}, format="json"),
            partial(b.post, f"/api/v1/orders/{conta.pk}/attach-commands/", {"commands": [str(cartao.pk)]}, format="json"),
        )

        with tenant_context(restaurant.account):
            na_conta = OrderItem.objects.filter(order=conta).exclude(status=OrderItem.STATUS_CANCELLED)
            for linha in na_conta:
                assert linha.command_item.status != CommandItem.STATUS_CANCELLED, "cancelado e cobrado ao mesmo tempo"
            itens = CommandItem.objects.filter(command=cartao)
            assert all(i.status == CommandItem.STATUS_CANCELLED for i in itens) or na_conta.count() == 2


@pytest.fixture
def pedido_pagavel(restaurant, branch, manager_user, produto):
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    with tenant_context(restaurant.account):
        dinheiro = PaymentMethod.objects.create(account=restaurant.account, restaurant=restaurant, branch=branch,
                                                name=f"Dinheiro {uuid.uuid4().hex[:4]}", method_type=PaymentMethod.TYPE_CASH)

    def novo():
        with tenant_context(restaurant.account):
            pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
            add_order_item(order=pedido, product=produto, quantity=2, user=manager_user)
            pedido.refresh_from_db()
        return pedido

    return novo, dinheiro


def test_clique_duplo_no_pagar_com_a_mesma_chave(manager_user, pedido_pagavel):
    novo, dinheiro = pedido_pagavel
    for _ in range(RODADAS):
        pedido = novo()
        chave = str(uuid.uuid4())
        corpo = {"payment_method": str(dinheiro.pk), "amount": "10.00"}
        a, b = _cliente(manager_user), _cliente(manager_user)

        _ao_mesmo_tempo(
            partial(a.post, f"/api/v1/orders/{pedido.pk}/pay/", corpo, format="json", HTTP_IDEMPOTENCY_KEY=chave),
            partial(b.post, f"/api/v1/orders/{pedido.pk}/pay/", corpo, format="json", HTTP_IDEMPOTENCY_KEY=chave),
        )

        with tenant_context(pedido.account):
            assert Payment.objects.filter(order=pedido, status=Payment.STATUS_APPROVED).count() == 1


def test_remover_o_mesmo_pagamento_duas_vezes(manager_user, pedido_pagavel):
    novo, dinheiro = pedido_pagavel
    for _ in range(RODADAS):
        pedido = novo()
        cliente = _cliente(manager_user)
        cliente.post(f"/api/v1/orders/{pedido.pk}/pay/", {"payment_method": str(dinheiro.pk), "amount": "10.00"}, format="json")
        with tenant_context(pedido.account):
            pagamento = Payment.objects.get(order=pedido)
        a, b = _cliente(manager_user), _cliente(manager_user)

        r1, r2 = _ao_mesmo_tempo(
            partial(a.delete, f"/api/v1/orders/{pedido.pk}/payments/{pagamento.pk}/"),
            partial(b.delete, f"/api/v1/orders/{pedido.pk}/payments/{pagamento.pk}/"),
        )

        assert 500 not in (r1.status_code, r2.status_code), (r1.content, r2.content)
        with tenant_context(pedido.account):
            pedido.refresh_from_db()
            assert (pedido.status, pedido.payment_status) == (Order.STATUS_OPEN, Order.PAYMENT_PENDING)
            assert Payment.objects.get(pk=pagamento.pk).status == Payment.STATUS_CANCELLED


def test_checkout_e_pagamento_ao_mesmo_tempo(manager_user, pedido_pagavel):
    """O pago nunca passa do total, e o status bate com o que foi recebido."""
    novo, dinheiro = pedido_pagavel
    for _ in range(RODADAS):
        pedido = novo()
        a, b = _cliente(manager_user), _cliente(manager_user)

        _ao_mesmo_tempo(
            partial(a.post, f"/api/v1/orders/{pedido.pk}/checkout/", {"service_fee_enabled": True}, format="json"),
            partial(b.post, f"/api/v1/orders/{pedido.pk}/pay/", {"payment_method": str(dinheiro.pk), "amount": "5.00"}, format="json"),
        )

        with tenant_context(pedido.account):
            pedido.refresh_from_db()
            pago = sum((p.amount for p in Payment.objects.filter(order=pedido, status=Payment.STATUS_APPROVED)), Decimal("0"))
            assert pago <= pedido.total
            if pago == 0:
                assert pedido.status == Order.STATUS_OPEN
            elif pago < pedido.total:
                assert (pedido.status, pedido.payment_status) == (Order.STATUS_AWAITING_PAYMENT, Order.PAYMENT_PARTIAL)
