"""O salão AGORA: quantas comandas estão em uso, quanto devem, quais são.

"Em uso" é a mesma regra da grade do PDV (`command_listing.anotar_estado`): ter
anotação PENDENTE que valha dinheiro (não cancelada nem cortesia), ou estar
presa a um pedido aberto do fluxo antigo. Uma regra diferente aqui faria o
relatório e o salão discordarem sobre o mesmo cartão.

"Em conta aberta" é a comanda cujo consumo já foi levado a uma conta que
ninguém pagou — o caso que trava o próximo cliente ("a comanda já está na
conta #42"), e por isso aparece à parte.
"""
from decimal import Decimal

from django.db.models import Exists, Max, Min, OuterRef, Q

ZERO = Decimal("0.00")


def reais(valor):
    """Duas casas sempre: a soma do SQLite devolve `50` onde o Postgres dá `50.00`."""
    return (valor or ZERO).quantize(ZERO)


def _cobravel():
    from apps.orders.models import CommandItem

    return (Q(command_items__command_status=CommandItem.STATUS_PENDENTE)
            & Q(command_items__deleted_at__isnull=True)
            & ~Q(command_items__status__in=[CommandItem.STATUS_CANCELLED, CommandItem.STATUS_COMPED]))


def _comandas(escopo):
    """As comandas ativas do escopo, com o estado de cada uma já anotado."""
    from apps.orders.models import CommandItem, Order, OrderItem
    from apps.restaurants.command_listing import anotar_estado
    from apps.restaurants.models import Command

    em_conta_aberta = OrderItem.objects.filter(
        command_item__command=OuterRef("pk"),
        command_item__command_status=CommandItem.STATUS_PENDENTE,
        order__status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
        order__deleted_at__isnull=True,
    )
    return anotar_estado(Command.objects.filter(is_active=True, **escopo)).annotate(
        aberta_desde=Min("command_items__launched_at", filter=_cobravel()),
        ultimo_lancamento=Max("command_items__launched_at", filter=_cobravel()),
        em_conta_aberta=Exists(em_conta_aberta),
    )


def _em_uso(comandas):
    return comandas.filter(Q(pendentes__gt=0) | Q(pedido_aberto=True))


def resumo(escopo):
    comandas = _comandas(escopo)
    em_uso = list(_em_uso(comandas).values("pendentes", "pendente_total", "em_conta_aberta"))
    cadastradas = comandas.count()
    return {
        "registered": cadastradas,
        "in_use": len(em_uso),
        "free": cadastradas - len(em_uso),
        "in_open_bill": sum(1 for c in em_uso if c["em_conta_aberta"]),
        "in_use_total": reais(sum((c["pendente_total"] or ZERO for c in em_uso), ZERO)),
        "in_use_items": sum(c["pendentes"] for c in em_uso),
    }


def lista(escopo):
    """As comandas em uso, a aberta há mais tempo primeiro."""
    linhas = (
        _em_uso(_comandas(escopo))
        .values("id", "number", "code", "customer_name", "current_table__number",
                "pendentes", "pendente_total", "aberta_desde", "ultimo_lancamento",
                "em_conta_aberta")
        .order_by("aberta_desde", "number")
    )
    return [
        {
            "id": str(linha["id"]),
            "number": linha["number"],
            "code": linha["code"],
            "customer_name": linha["customer_name"],
            "table": linha["current_table__number"] or "",
            "items": linha["pendentes"],
            "total": reais(linha["pendente_total"]),
            "open_since": linha["aberta_desde"],
            "last_launch": linha["ultimo_lancamento"],
            "in_open_bill": bool(linha["em_conta_aberta"]),
        }
        for linha in linhas
    ]
