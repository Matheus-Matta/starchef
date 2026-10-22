"""O dashboard em poucas consultas, com os mesmos números.

Medido na nuvem: ~1 s DENTRO do Django (o nginx conectava em 0 ms). Eram
~15 consultas, seis delas passadas separadas sobre os pedidos de hoje, e
todas filtrando por `opened_at__date`: no Postgres isso converte o fuso de
CADA linha antes de comparar, então nenhuma usava o índice
(restaurant, opened_at) e cada uma varria a tabela de pedidos inteira.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db
URL = "/api/v1/reports/dashboard/"


def _pedido(restaurant, branch, user, quando, total, status, pagamento):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user)
    Order.all_objects.filter(pk=pedido.pk).update(
        opened_at=quando, total=Decimal(total), status=status, payment_status=pagamento,
    )


def _as(dia, hora):
    return timezone.make_aware(datetime.combine(dia, time(hora, 30)))


@pytest.fixture
def vendas(restaurant, branch, manager_user):
    hoje = timezone.localdate()
    pago, aberto, cancelado = Order.STATUS_PAID, Order.STATUS_OPEN, Order.STATUS_CANCELLED
    quitado, pendente = Order.PAYMENT_PAID, Order.PAYMENT_PENDING
    _pedido(restaurant, branch, manager_user, _as(hoje, 12), "30.00", pago, quitado)
    _pedido(restaurant, branch, manager_user, _as(hoje, 12), "10.00", pago, quitado)
    _pedido(restaurant, branch, manager_user, _as(hoje, 19), "20.00", pago, quitado)
    _pedido(restaurant, branch, manager_user, _as(hoje, 13), "99.00", aberto, pendente)
    _pedido(restaurant, branch, manager_user, _as(hoje, 13), "50.00", cancelado, pendente)
    # 23:30 de ontem: no fuso de Brasília é ONTEM, mesmo já sendo hoje em UTC.
    _pedido(restaurant, branch, manager_user, _as(hoje - timedelta(days=1), 23), "7.00", pago, quitado)
    _pedido(restaurant, branch, manager_user, _as(hoje - timedelta(days=40), 12), "1000.00", pago, quitado)
    return hoje


def test_os_numeros_de_hoje(api_client, restaurant, vendas):
    dados = api_client.get(URL, {"restaurant": str(restaurant.pk)}).json()

    assert Decimal(str(dados["total_sold_today"])) == Decimal("60.00")
    assert dados["orders_count"] == 5
    assert dados["open_orders"] == 1
    assert dados["paid_orders"] == 3
    assert dados["cancelled_orders"] == 1
    assert Decimal(str(dados["average_ticket"])) == Decimal("20.00")
    por_hora = {b["label"]: Decimal(str(b["total"])) for b in dados["sales_today_by_hour"]}
    assert por_hora["12h"] == Decimal("40.00") and por_hora["18h"] == Decimal("20.00")
    semana = {d["date"]: Decimal(str(d["total"])) for d in dados["sales_last_7_days"]}
    assert semana[vendas.isoformat()] == Decimal("60.00")
    assert semana[(vendas - timedelta(days=1)).isoformat()] == Decimal("7.00")
    assert len(dados["sales_last_7_days"]) == 7
    mes = {d["date"]: Decimal(str(d["total"])) for d in dados["sales_current_month"]}
    assert mes[vendas.isoformat()] == Decimal("60.00")
    assert sum(mes.values()) == Decimal("60.00") + (Decimal("7.00") if vendas.day > 1 else 0)
    tipos = {t["order_type"]: t for t in dados["sales_by_order_type"]}
    assert tipos[Order.TYPE_COUNTER]["count"] == 3


def test_poucas_consultas(api_client, restaurant, vendas):
    with CaptureQueriesContext(connection) as ctx:
        resposta = api_client.get(URL, {"restaurant": str(restaurant.pk)})
    assert resposta.status_code == 200
    consultas = [q["sql"] for q in ctx.captured_queries if q["sql"].lstrip().startswith("SELECT")]
    pedidos = [q for q in consultas if 'FROM "orders_order"' in q]
    assert len(pedidos) <= 3, f"{len(pedidos)} consultas em orders_order"


def test_o_resumo_do_topo_calcula_so_o_que_o_topo_mostra(api_client, restaurant, vendas):
    """O layout de TODA página pedia o dashboard inteiro a cada 30 s — gráfico
    do mês e estoque incluídos — para mostrar três números: ~700 ms por vez,
    por aba aberta, o dia todo."""
    with CaptureQueriesContext(connection) as ctx:
        dados = api_client.get(URL, {"restaurant": str(restaurant.pk), "resumo": "1"}).json()

    assert (dados["orders_count"], dados["open_orders"]) == (5, 1)
    assert "kitchen_open_items" in dados
    assert "sales_current_month" not in dados and "low_stock" not in dados
    # O que a requisição autenticada sempre consulta (usuário, perfil) não conta.
    do_relatorio = [q["sql"] for q in ctx.captured_queries
                    if '"orders_' in q["sql"] or '"stock_' in q["sql"]]
    assert len(do_relatorio) == 2, do_relatorio
