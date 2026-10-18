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

Mostra SEMPRE a semana atual, de domingo a sábado, independente do período
do relatório: é o retrato do movimento de agora, e um mês inteiro em linhas
diárias virava uma tabela que ninguém lê. Os dias que ainda não chegaram
aparecem vazios.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

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


def semana_atual(hoje=None):
    """Domingo e sábado da semana de `hoje` (no fuso da loja)."""
    hoje = hoje or timezone.localdate()
    domingo = hoje - timedelta(days=(hoje.weekday() + 1) % 7)
    return domingo, domingo + timedelta(days=6)


def mapa_de_calor(*, filtros, hoje=None):
    from apps.orders.models import CommandItem, Order, OrderItem

    inicio, fim = semana_atual(hoje)
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

    chave = "launched_at__date"
    comanda, avulso = _contar(anotados, chave), _contar(balcao, chave)
    dias = [inicio + timedelta(days=n) for n in range(7)]
    linhas = [
        {"key": dia.isoformat(), "label": DIAS_DA_SEMANA[n], "cells": _celulas(comanda, avulso, dia)}
        for n, dia in enumerate(dias)
    ]
    return {"start": inicio.isoformat(), "end": fim.isoformat(), "rows": linhas}
