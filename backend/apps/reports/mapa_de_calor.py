"""Mapa de calor do movimento: em que dia e em que hora a casa vendeu.

Duas origens, contadas pelo horário em que o item ENTROU:

- comanda: o `CommandItem`, na hora em que o garçom anotou. A hora do pedido
  que pagou a comanda não serve: o almoço anotado ao meio-dia e pago às 15h
  apareceria às 15h, e o pico do salão sumiria do mapa;
- balcão: o item de pedido pago que não veio de comanda (balcão, retirada,
  entrega), na hora em que foi lançado.

Cancelado e cortesia ficam fora. A comanda conta mesmo antes de paga: a
pergunta é "quando o salão estava cheio", e o cartão ainda aberto também é
gente consumindo.

Período de até 31 dias sai dia a dia; acima disso, por dia da semana — um ano
em linhas diárias seriam 365 linhas que ninguém lê.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

DIAS_POR_LINHA = 31
DIAS_DA_SEMANA = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]


def _contar(itens, chave):
    linhas = itens.values(chave, "launched_at__hour").annotate(itens=Count("id"), valor=Sum("total_price"))
    return {(linha[chave], linha["launched_at__hour"]): linha for linha in linhas}


def _celulas(comanda, balcao, chave):
    celulas = []
    for hora in range(24):
        c = comanda.get((chave, hora), {})
        b = balcao.get((chave, hora), {})
        celulas.append({
            "hour": hora,
            "command_items": c.get("itens", 0),
            "command_total": c.get("valor") or Decimal("0.00"),
            "counter_items": b.get("itens", 0),
            "counter_total": b.get("valor") or Decimal("0.00"),
        })
    return celulas


def mapa_de_calor(*, filtros, inicio, fim):
    from apps.orders.models import CommandItem, Order, OrderItem

    fim = fim or timezone.localdate()
    inicio = inicio or fim - timedelta(days=6)
    fora = [CommandItem.STATUS_CANCELLED, CommandItem.STATUS_COMPED]
    periodo = {"launched_at__date__gte": inicio, "launched_at__date__lte": fim}

    anotados = CommandItem.objects.filter(**filtros, **periodo).exclude(status__in=fora)
    # O pedido pago em QUALQUER data: o período é o do item. Filtrar pela
    # abertura do pedido perderia o item lançado depois da meia-noite numa
    # conta aberta às 23h50.
    pagos = Order.objects.filter(**filtros).filter(Q(payment_status=Order.PAYMENT_PAID) | Q(status=Order.STATUS_PAID))
    balcao = OrderItem.objects.filter(
        order_id__in=pagos.values("pk"), command_item__isnull=True, command__isnull=True, **periodo
    ).exclude(status__in=fora)

    if (fim - inicio).days < DIAS_POR_LINHA:
        chave = "launched_at__date"
        comanda, avulso = _contar(anotados, chave), _contar(balcao, chave)
        dias = [inicio + timedelta(days=n) for n in range((fim - inicio).days + 1)]
        linhas = [
            {"key": dia.isoformat(), "label": DIAS_DA_SEMANA[(dia.weekday() + 1) % 7],
             "cells": _celulas(comanda, avulso, dia)}
            for dia in dias
        ]
        return {"mode": "day", "rows": linhas}

    chave = "launched_at__week_day"  # 1 = domingo … 7 = sábado
    comanda, avulso = _contar(anotados, chave), _contar(balcao, chave)
    linhas = [
        {"key": str(n), "label": DIAS_DA_SEMANA[n - 1], "cells": _celulas(comanda, avulso, n)}
        for n in range(1, 8)
    ]
    return {"mode": "weekday", "rows": linhas}
