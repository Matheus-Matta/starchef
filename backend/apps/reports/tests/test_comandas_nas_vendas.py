"""O relatório de vendas conta as comandas que foram pagas, não só os pedidos.

Um pedido pode pagar várias comandas (a família que junta quatro cartões numa
conta), então 100 pedidos podem ser 150 comandas. O ticket por comanda divide
o valor SÓ dos pedidos que tiveram comanda: misturar a venda do balcão no
numerador inflaria o ticket de quem nunca usou cartão.
"""
from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import Order, OrderItem
from apps.reports.tests.test_waiter_sales_report import product  # noqa: F401 — fixture
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


def test_conta_cada_comanda_do_pedido_e_divide_so_a_venda_com_comanda(
    api_client, account, restaurant, branch, manager_user, product  # noqa: F811
):
    tenant = {"account": account, "restaurant": restaurant, "branch": branch}
    c1, c2, c3, c4 = (Command.objects.create(**tenant, number=n) for n in (1, 2, 3, 4))

    def pedido(seq, total, comandas, tipo=Order.TYPE_COMMAND, status=Order.STATUS_PAID, command=None):
        order = Order.objects.create(**tenant, sequence=seq, order_type=tipo, status=status,
                                     payment_status=Order.PAYMENT_PAID if status == Order.STATUS_PAID
                                     else Order.PAYMENT_PENDING, total=total, command=command)
        for comanda in comandas:  # dois itens da mesma comanda contam UMA vez
            for _ in range(2):
                OrderItem.objects.create(**tenant, order=order, product=product, quantity="1.000",
                                         unit_price="10.00", total_price="10.00", command=comanda)
        return order

    pedido(1, "90.00", [c1, c2, c3])  # a família: três cartões numa conta
    pedido(2, "30.00", [c4])
    pedido(3, "50.00", [], tipo=Order.TYPE_COUNTER)  # balcão: fora da conta da comanda
    pedido(4, "40.00", [], command=c1)  # legado: só o Order.command, sem item marcado
    pedido(5, "99.00", [c2], status=Order.STATUS_OPEN)  # não pago: fora
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    dados = api_client.get("/api/v1/reports/sales/").data

    assert dados["commands_count"] == 5
    assert Decimal(str(dados["commands_total"])) == Decimal("160.00")
    assert Decimal(str(dados["commands_average_ticket"])) == Decimal("32.00")


def test_sem_comanda_o_ticket_e_zero_e_nao_divide_por_zero(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    dados = api_client.get("/api/v1/reports/sales/").data

    assert dados["commands_count"] == 0
    assert Decimal(str(dados["commands_average_ticket"])) == Decimal("0.00")
