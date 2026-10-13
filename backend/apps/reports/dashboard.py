"""Os números da visão geral, em poucas consultas.

Medido na nuvem: ~1 s DENTRO do Django. Eram ~15 consultas, seis delas
passadas separadas sobre os pedidos de hoje (total, quantidade, abertos,
pagos, cancelados, ticket), e todas filtrando por `opened_at__date`. No
Postgres esse filtro converte o fuso de CADA linha antes de comparar: nenhuma
usava o índice (restaurant, opened_at), e cada uma varria a tabela de pedidos
inteira — que só cresce.

Agora o período vira uma FAIXA de horário (`opened_at >= início`, `< fim`), que
usa o índice, e o que é sobre o mesmo conjunto sai numa consulta só.
"""
from calendar import monthrange
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

#: As faixas do gráfico de hoje (início inclusivo, fim exclusivo).
FAIXAS_DO_DIA = [(8, "08h"), (10, "10h"), (12, "12h"), (14, "14h"),
                 (16, "16h"), (18, "18h"), (20, "20h"), (22, "22h")]


def inicio_do_dia(dia):
    """Meia-noite de `dia` no fuso do restaurante (TIME_ZONE), com fuso."""
    return timezone.make_aware(datetime.combine(dia, time.min))


def faixa(primeiro_dia, ultimo_dia):
    """Filtro de `opened_at` do primeiro dia ao último, inteiros."""
    return {"opened_at__gte": inicio_do_dia(primeiro_dia),
            "opened_at__lt": inicio_do_dia(ultimo_dia + timedelta(days=1))}


def resumo_de_hoje(pedidos_de_hoje, order_model):
    """Total, quantidade, abertos, pagos, cancelados e ticket: UMA consulta."""
    pago = Q(payment_status=order_model.PAYMENT_PAID)
    linha = pedidos_de_hoje.aggregate(
        orders_count=Count("id"),
        open_orders=Count("id", filter=~Q(status__in=[order_model.STATUS_PAID,
                                                       order_model.STATUS_CANCELLED])),
        paid_orders=Count("id", filter=pago),
        cancelled_orders=Count("id", filter=Q(status=order_model.STATUS_CANCELLED)),
        total_sold_today=Sum("total", filter=pago),
    )
    pagos = linha["paid_orders"] or 0
    vendido = linha["total_sold_today"] or 0
    return {
        **linha,
        "total_sold_today": vendido,
        # A média dos pagos é a soma deles sobre a quantidade: a mesma conta do
        # `Avg`, sem uma passada a mais.
        "average_ticket": (Decimal(vendido) / pagos).quantize(Decimal("0.01")) if pagos else 0,
    }


def vendas_por_periodo(pagos_no_periodo, hoje):
    """Por hora (hoje), últimos 7 dias e mês corrente — de UMA leitura.

    Os pedidos pagos do intervalo que cobre os três (do 1º do mês, ou de 6
    dias atrás, até hoje), só `opened_at` e `total`; o resto é soma em Python.
    """
    por_dia, por_faixa = {}, {rotulo: 0 for _, rotulo in FAIXAS_DO_DIA}
    for aberto_em, total in pagos_no_periodo.values_list("opened_at", "total"):
        local = timezone.localtime(aberto_em)
        dia = local.date()
        por_dia[dia] = por_dia.get(dia, 0) + (total or 0)
        if dia == hoje:
            for inicio, rotulo in reversed(FAIXAS_DO_DIA):
                if inicio <= local.hour < inicio + 2:
                    por_faixa[rotulo] += total or 0
                    break
    primeiro_do_mes = hoje.replace(day=1)
    dias_no_mes = monthrange(hoje.year, hoje.month)[1]
    return {
        "sales_today_by_hour": [
            {"date": hoje.isoformat(), "label": rotulo, "total": por_faixa[rotulo]}
            for _, rotulo in FAIXAS_DO_DIA
        ],
        "sales_last_7_days": [
            {"date": dia.isoformat(), "label": dia.strftime("%a"), "total": por_dia.get(dia, 0)}
            for dia in (hoje - timedelta(days=atras) for atras in range(6, -1, -1))
        ],
        "sales_current_month": [
            {"date": dia.isoformat(), "label": dia.strftime("%d"), "total": por_dia.get(dia, 0)}
            for dia in (primeiro_do_mes + timedelta(days=n) for n in range(dias_no_mes))
        ],
    }


def inicio_do_periodo(hoje):
    """O primeiro dia que os gráficos de 7 dias e do mês precisam."""
    return min(hoje.replace(day=1), hoje - timedelta(days=6))
