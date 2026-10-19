"""O que as comandas fizeram no PERÍODO: pagas, ticket, uso, perdas, tempo.

* **Pagas** e **ticket médio** vêm de `comandas_nas_vendas.py`, a mesma conta
  do relatório de vendas: uma comanda paga duas vezes no dia (dois clientes)
  conta duas, e o ticket divide só o valor dos pedidos que tiveram comanda.
* **Usadas** é cartão distinto com algum lançamento no período.
* **Perda** é o consumo encerrado SEM venda: a conta cancelada leva as
  anotações a `cancelado` (`conclude_items_of_order(billed=False)`).
* **Permanência** vai do primeiro lançamento ao pagamento, por uso.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Max, Min, Q, Sum

from apps.reports.comandas_agora import reais

ZERO = Decimal("0.00")


def _valendo(queryset):
    """Só o que vale dinheiro: item cancelado ou cortesia não é consumo."""
    from apps.orders.models import CommandItem

    return queryset.exclude(status__in=[CommandItem.STATUS_CANCELLED, CommandItem.STATUS_COMPED])


def _entre(campo, inicio, fim):
    return {**({f"{campo}__gte": inicio} if inicio else {}), **({f"{campo}__lte": fim} if fim else {})}


def resumo(escopo, inicio, fim):
    from apps.orders.models import CommandItem, Order
    from apps.reports.comandas_nas_vendas import resumo as pagas_nas_vendas

    pagos = Order.objects.filter(
        Q(payment_status=Order.PAYMENT_PAID) | Q(status=Order.STATUS_PAID),
        **escopo, **_entre("opened_at", inicio, fim),
    )
    pagas = pagas_nas_vendas(pagos)
    lancados = _valendo(CommandItem.objects.filter(**escopo, **_entre("launched_at", inicio, fim)))
    cobrados = _valendo(CommandItem.objects.filter(
        **escopo, command_status=CommandItem.STATUS_COBRADO,
        **_entre("command_closed_at", inicio, fim)))
    perdidos = _valendo(CommandItem.objects.filter(
        **escopo, command_status=CommandItem.STATUS_CANCELADO,
        **_entre("command_closed_at", inicio, fim)))
    soma_lancada = lancados.aggregate(n=Count("id"), total=Sum("total_price"),
                                      cartoes=Count("command_id", distinct=True))
    soma_perdida = perdidos.aggregate(n=Count("id"), total=Sum("total_price"))
    linhas_cobradas = cobrados.count()
    return {
        "paid": pagas["commands_count"],
        "paid_total": reais(pagas["commands_total"]),
        "average_ticket": pagas["commands_average_ticket"],
        "used": soma_lancada["cartoes"] or 0,
        "launched_items": soma_lancada["n"] or 0,
        "launched_total": reais(soma_lancada["total"]),
        "lost_items": soma_perdida["n"] or 0,
        "lost_total": reais(soma_perdida["total"]),
        "average_items_per_paid": _media(linhas_cobradas, pagas["commands_count"]),
        "average_stay_minutes": _permanencia(cobrados),
    }


def _media(soma, quantidade):
    if not quantidade:
        return ZERO
    return (Decimal(soma) / quantidade).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _permanencia(cobrados):
    """Minutos médios do primeiro lançamento ao pagamento, por uso da comanda.

    Um uso é a comanda + o instante em que a conta dela foi paga: a mesma
    comanda paga duas vezes no dia são dois usos, cada um com o seu tempo.
    """
    usos = (cobrados.values("command_id", "command_closed_at")
            .annotate(inicio=Min("launched_at")))
    minutos = [(u["command_closed_at"] - u["inicio"]).total_seconds() / 60
               for u in usos if u["command_closed_at"] and u["inicio"]]
    if not minutos:
        return None
    return round(sum(minutos) / len(minutos), 1)


def por_comanda(escopo, inicio, fim):
    """Cada número de comanda: quantas vezes foi paga, itens e valor."""
    from apps.orders.models import CommandItem

    linhas = (
        _valendo(CommandItem.objects.filter(
            **escopo, command_status=CommandItem.STATUS_COBRADO,
            **_entre("command_closed_at", inicio, fim)))
        .values("command__number")
        .annotate(uses=Count("command_closed_at", distinct=True), items=Count("id"),
                  total=Sum("total_price"), last_use=Max("command_closed_at"))
        .order_by("-total", "command__number")
    )
    return [
        {"number": linha["command__number"], "uses": linha["uses"], "items": linha["items"],
         "total": reais(linha["total"]), "last_use": linha["last_use"]}
        for linha in linhas
    ]
