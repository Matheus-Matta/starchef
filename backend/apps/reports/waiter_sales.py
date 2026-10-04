from django.db.models import Case, CharField, Count, F, Sum, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce

from apps.orders.models import OrderItem
from apps.orders.operator_code import CHAVE


def sales_by_waiter(orders, tenant_manager):
    """Agrupa itens vendidos pelo código do garçom ou pelo login lançador."""
    return (
        tenant_manager(OrderItem)
        .filter(order__in=orders)
        .exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED])
        .annotate(
            operator_code=Coalesce(
                KeyTextTransform(CHAVE, "metafields"),
                KeyTextTransform(CHAVE, "command_item__metafields"),
                Value(""),
                output_field=CharField(),
            ),
            operator_name=Case(
                When(
                    operator_code="",
                    then=Coalesce(
                        F("launched_by__username"),
                        F("command_item__launched_by__username"),
                        Value("Não identificado"),
                        output_field=CharField(),
                    ),
                ),
                default=Value(""),
                output_field=CharField(),
            ),
            operator_username=Case(
                When(
                    operator_code="",
                    then=Coalesce(
                        F("launched_by__username"),
                        F("command_item__launched_by__username"),
                        Value(""),
                        output_field=CharField(),
                    ),
                ),
                default=Value(""),
                output_field=CharField(),
            ),
        )
        # O código identifica o garçom mesmo que o item tenha sido copiado ou
        # consolidado por logins de caixa diferentes.
        .values("operator_code", "operator_name", "operator_username")
        .annotate(
            total=Sum("total_price"),
            count=Count("order_id", distinct=True),
            items=Count("id"),
        )
        .order_by("-total")
    )
