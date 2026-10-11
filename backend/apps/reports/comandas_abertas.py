"""Quanto dinheiro está em comandas abertas, para a visão geral.

Mesma regra da lista de comandas do PDV (`command_listing.anotar_estado`):
anotação PENDENTE, não cancelada nem cortesia. O item continua pendente
enquanto a conta que o incluiu não for paga, então nada é somado duas vezes
nem some no meio do caminho entre a comanda e o caixa.
"""
from decimal import Decimal

from django.db.models import Count, Sum


def resumo(filtros):
    from apps.orders.models import CommandItem

    pendentes = CommandItem.objects.filter(
        command_status=CommandItem.STATUS_PENDENTE, **filtros
    ).exclude(status__in=[CommandItem.STATUS_CANCELLED, CommandItem.STATUS_COMPED])
    soma = pendentes.aggregate(total=Sum("total_price"), cartoes=Count("command_id", distinct=True))
    return {
        "open_commands_total": soma["total"] or Decimal("0.00"),
        "open_commands_count": soma["cartoes"] or 0,
    }
