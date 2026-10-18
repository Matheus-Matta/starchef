"""O mapa de calor mostra a semana atual e põe cada item na hora em que ENTROU.

O item da comanda conta na hora da anotação, não na do pagamento: o almoço
anotado ao meio-dia e pago às 15h sumiria do pico do salão. O balcão conta o item
de pedido pago que não veio de comanda — e o item que veio de comanda não
entra de novo como balcão quando a conta é paga.

A semana é sempre a atual (domingo a sábado), qualquer que seja o período do
relatório: um mês em linhas diárias virava uma tabela que ninguém lia.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import CommandItem, Order, OrderItem
from apps.reports.mapa_de_calor import semana_atual
from apps.reports.tests.test_waiter_sales_report import product  # noqa: F401 — fixture
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db
SP = ZoneInfo("America/Sao_Paulo")


def _em(dia, hora, minuto=0):
    return datetime.combine(dia, time(hora, minuto), tzinfo=SP)


def test_semana_atual_vai_de_domingo_a_sabado():
    assert semana_atual(date(2026, 10, 14)) == (date(2026, 10, 11), date(2026, 10, 17))  # quarta
    assert semana_atual(date(2026, 10, 11)) == (date(2026, 10, 11), date(2026, 10, 17))  # domingo
    assert semana_atual(date(2026, 10, 17)) == (date(2026, 10, 11), date(2026, 10, 17))  # sábado


def test_comanda_na_hora_da_anotacao_e_balcao_na_hora_do_lancamento(
    api_client, account, restaurant, branch, manager_user, product  # noqa: F811
):
    tenant = {"account": account, "restaurant": restaurant, "branch": branch}
    item = {"product": product, "quantity": "1.000", "unit_price": "10.00", "total_price": "10.00"}
    domingo, _ = semana_atual()
    quarta = domingo + timedelta(days=3)
    comanda = Command.objects.create(**tenant, number=1)
    anotado = CommandItem.objects.create(**tenant, **item, command=comanda)
    cancelado = CommandItem.objects.create(**tenant, **item, command=comanda, status=CommandItem.STATUS_CANCELLED)
    semana_passada = CommandItem.objects.create(**tenant, **item, command=comanda)
    pago = Order.objects.create(**tenant, sequence=1, order_type=Order.TYPE_COUNTER, status=Order.STATUS_PAID,
                                payment_status=Order.PAYMENT_PAID, total="30.00")
    balcao = OrderItem.objects.create(**tenant, **item, order=pago)
    da_comanda = OrderItem.objects.create(**tenant, **item, order=pago, command=comanda, command_item=anotado)
    CommandItem.all_objects.filter(pk__in=[anotado.pk, cancelado.pk]).update(launched_at=_em(quarta, 12, 30))
    CommandItem.all_objects.filter(pk=semana_passada.pk).update(launched_at=_em(quarta - timedelta(days=7), 12))
    OrderItem.all_objects.filter(pk=balcao.pk).update(launched_at=_em(quarta, 9, 5))
    OrderItem.all_objects.filter(pk=da_comanda.pk).update(launched_at=_em(quarta, 15))
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    mapa = api_client.get("/api/v1/reports/sales/").data["heatmap"]

    assert [linha["label"] for linha in mapa["rows"]] == [
        "Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado",
    ]
    assert mapa["start"] == domingo.isoformat()
    dia = {celula["hour"]: celula for celula in mapa["rows"][3]["cells"]}
    assert dia[12]["command_items"] == 1  # o cancelado e o da semana passada ficam fora
    assert Decimal(str(dia[12]["command_total"])) == Decimal("10.00")
    assert dia[9]["counter_items"] == 1
    assert dia[15]["counter_items"] == 0  # já contado na anotação, ao meio-dia


def test_o_periodo_do_relatorio_nao_muda_o_mapa(api_client, manager_user):
    """Um ano inteiro no filtro continua mostrando só a semana atual."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    mapa = api_client.get("/api/v1/reports/sales/", {"date_from": "2026-01-01", "date_to": "2026-12-31"}).data[
        "heatmap"
    ]

    domingo, sabado = semana_atual()
    assert (mapa["start"], mapa["end"]) == (domingo.isoformat(), sabado.isoformat())
    assert len(mapa["rows"]) == 7
    assert all(len(linha["cells"]) == 24 for linha in mapa["rows"])
