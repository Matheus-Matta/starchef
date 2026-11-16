"""O filtro de data do KDS é intervalo de instantes, no fuso da loja.

`launched_at__date` aplicava uma função na coluna, o Postgres não usava
índice, e cada leitura do quadro varria a tabela de itens inteira. O
intervalo precisa continuar dizendo exatamente "o dia da loja".
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.kitchen.views import KitchenItemFilter
from apps.orders.models import OrderItem

pytestmark = pytest.mark.django_db


def _no_fuso(dia, hora, minuto):
    return timezone.make_aware(datetime.combine(dia, time(hora, minuto)))


def test_o_dia_e_o_da_loja_nas_duas_pontas(account, restaurant, branch, manager_user):
    import uuid

    from apps.core.tenant import tenant_context
    from apps.menu.models import Product
    from apps.orders.models import Order
    from apps.orders.services import add_order_item, create_order

    with tenant_context(account):
        pedido = create_order(restaurant=restaurant, branch=branch,
                              order_type=Order.TYPE_COUNTER, user=manager_user)
        for n in range(4):  # produtos diferentes: o mesmo produto vira um item só
            produto = Product.objects.create(
                account=account, restaurant=restaurant, branch=branch, name=f"Prato {n}",
                internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("10.00"),
            )
            add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)

    hoje = timezone.localdate()
    ontem, amanha = hoje - timedelta(days=1), hoje + timedelta(days=1)
    itens = list(OrderItem.all_objects.filter(order=pedido).order_by("id"))
    lancamentos = [_no_fuso(ontem, 23, 50), _no_fuso(hoje, 0, 10),
                   _no_fuso(hoje, 23, 50), _no_fuso(amanha, 0, 10)]
    for item, quando in zip(itens, lancamentos, strict=False):
        OrderItem.all_objects.filter(pk=item.pk).update(launched_at=quando)

    filtro = KitchenItemFilter(
        {"launched_after": hoje.isoformat(), "launched_before": hoje.isoformat()},
        queryset=OrderItem.all_objects.filter(order=pedido),
    )
    assert set(filtro.qs.values_list("id", flat=True)) == {itens[1].id, itens[2].id}
    assert "::date" not in str(filtro.qs.query).lower()
