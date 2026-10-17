"""O mapa de calor põe cada item na hora em que ele ENTROU.

O item da comanda conta na hora da anotação, não na do pagamento: o almoço
anotado ao meio-dia e pago às 15h sumiria do pico do salão. O balcão conta o item
de pedido pago que não veio de comanda — e o item que veio de comanda não
entra de novo como balcão quando a conta é paga.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import CommandItem, Order, OrderItem
from apps.reports.tests.test_waiter_sales_report import product  # noqa: F401 — fixture
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db
SP = ZoneInfo("America/Sao_Paulo")


def test_comanda_na_hora_da_anotacao_e_balcao_na_hora_do_lancamento(
    api_client, account, restaurant, branch, manager_user, product  # noqa: F811
):
    tenant = {"account": account, "restaurant": restaurant, "branch": branch}
    item = {"product": product, "quantity": "1.000", "unit_price": "10.00", "total_price": "10.00"}
    comanda = Command.objects.create(**tenant, number=1)
    anotado = CommandItem.objects.create(**tenant, **item, command=comanda)
    cancelado = CommandItem.objects.create(**tenant, **item, command=comanda, status=CommandItem.STATUS_CANCELLED)
    pago = Order.objects.create(**tenant, sequence=1, order_type=Order.TYPE_COUNTER, status=Order.STATUS_PAID,
                                payment_status=Order.PAYMENT_PAID, total="30.00")
    balcao = OrderItem.objects.create(**tenant, **item, order=pago)
    da_comanda = OrderItem.objects.create(**tenant, **item, order=pago, command=comanda, command_item=anotado)
    meio_dia = datetime(2026, 10, 14, 12, 30, tzinfo=SP)
    CommandItem.all_objects.filter(pk__in=[anotado.pk, cancelado.pk]).update(launched_at=meio_dia)
    OrderItem.all_objects.filter(pk=balcao.pk).update(launched_at=datetime(2026, 10, 14, 9, 5, tzinfo=SP))
    OrderItem.all_objects.filter(pk=da_comanda.pk).update(launched_at=datetime(2026, 10, 14, 15, 0, tzinfo=SP))
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    mapa = api_client.get("/api/v1/reports/sales/", {"date_from": "2026-10-13", "date_to": "2026-10-14"}).data[
        "heatmap"
    ]

    assert mapa["mode"] == "day"
    assert [linha["key"] for linha in mapa["rows"]] == ["2026-10-13", "2026-10-14"]
    dia = {celula["hour"]: celula for celula in mapa["rows"][1]["cells"]}
    assert dia[12]["command_items"] == 1
    assert Decimal(str(dia[12]["command_total"])) == Decimal("10.00")
    assert dia[9]["counter_items"] == 1
    assert dia[15]["counter_items"] == 0  # já contado na anotação, ao meio-dia
    assert sum(c["command_items"] + c["counter_items"] for c in mapa["rows"][0]["cells"]) == 0


def test_periodo_longo_agrupa_por_dia_da_semana(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    mapa = api_client.get("/api/v1/reports/sales/", {"date_from": "2026-01-01", "date_to": "2026-12-31"}).data[
        "heatmap"
    ]

    assert mapa["mode"] == "weekday"
    assert [linha["label"] for linha in mapa["rows"]][0] == "Domingo"
    assert len(mapa["rows"][0]["cells"]) == 24
