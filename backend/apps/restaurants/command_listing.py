"""O estado de muitas comandas numa consulta só.

`Command.em_uso` e o serializer perguntam ao banco cartão por cartão — quatro
consultas cada. Com 500 comandas abertas a lista do PDV custava um segundo por
página, e o PDV relê a lista a cada comanda alterada.

Estas anotações respondem as MESMAS perguntas, com as mesmas regras, para a
página inteira:

- pendente = anotação PENDENTE, não cancelada nem cortesia, não apagada
  (`billable_items_of`);
- em uso = ter pendente OU estar presa a um pedido ainda aberto (o fluxo
  antigo, em que o consumo mora no pedido).

Precisa ser aplicada DEPOIS do mixin de tenant: ele remonta o queryset a
partir do model e descartava a anotação declarada no corpo da classe.
"""
from decimal import Decimal

from django.db.models import BooleanField, Case, Count, DecimalField, Exists, OuterRef, Q, Sum, Value, When
from django.db.models.functions import Coalesce


def anotar_estado(queryset):
    from apps.orders.models import CommandItem, Order

    cobravel = (
        Q(command_items__command_status=CommandItem.STATUS_PENDENTE)
        & Q(command_items__deleted_at__isnull=True)
        & ~Q(command_items__status__in=[CommandItem.STATUS_CANCELLED, CommandItem.STATUS_COMPED])
    )
    anotado = queryset.annotate(
        pendentes=Count("command_items", filter=cobravel, distinct=True),
        pendente_total=Coalesce(
            Sum("command_items__total_price", filter=cobravel),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        pedido_aberto=Exists(
            Order.all_objects.filter(
                pk=OuterRef("current_order_id"),
                status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            )
        ),
    )
    # O `status` da tela ("Livre"/"Em uso") como valor do banco: é por ele que
    # a coluna ordena todas as páginas, não só a que está aberta.
    anotado = anotado.annotate(
        ordem_do_status=Case(
            When(Q(pendentes__gt=0) | Q(pedido_aberto=True), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
    )
    # A contagem vira GROUP BY, e o Django ignora `Meta.ordering` em consulta
    # agrupada: sem isto a grade saía embaralhada. `?ordering=` continua
    # valendo — o filtro de ordenação roda depois e substitui esta.
    if not queryset.query.order_by:
        anotado = anotado.order_by(*queryset.model._meta.ordering)
    return anotado
