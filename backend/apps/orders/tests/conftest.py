"""Cenário compartilhado dos testes de conta agrupada: a mesa da família.

Quatro comandas numa mesa, cada uma com o pedido de trabalho dela — que é
exatamente o desenho que a funcionalidade preserva durante o serviço.
"""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import PaymentMethod
from apps.restaurants.models import Command, Table, TableSector


@pytest.fixture
def contexto_tenant(account):
    """A conta corrente, como o middleware a deixaria.

    Sem ela `TenantManager` devolve queryset vazio para tudo, e o teste falha
    com "não existe" onde o problema real é só a falta de contexto.
    """
    with tenant_context(account):
        yield account


@pytest.fixture
def categoria(contexto_tenant, account, restaurant, branch):
    return ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Lanches"
    )


@pytest.fixture
def produto(account, restaurant, branch, categoria):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="X-Burger", internal_code=f"X{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"),
        production_sector=Product.SECTOR_KITCHEN,
    )


@pytest.fixture
def mesa(contexto_tenant, account, restaurant, branch):
    sector = TableSector.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Salao"
    )
    return Table.objects.create(
        account=account, restaurant=restaurant, branch=branch, sector=sector,
        number="1", capacity=4,
    )


@pytest.fixture
def produto_barato(account, restaurant, branch, categoria):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="Refrigerante", internal_code=f"R{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("10.05"),
        production_sector=Product.SECTOR_BAR,
    )


@pytest.fixture
def dinheiro(account, restaurant, branch):
    return PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Dinheiro", method_type=PaymentMethod.TYPE_CASH,
    )


@pytest.fixture
def sem_caixa_obrigatorio(restaurant):
    """O caixa aberto não é o assunto destes testes."""
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    return restaurant


def abrir_comanda_com_item(*, account, restaurant, branch, user, product, quantity=1, table=None):
    """Uma comanda nova, ocupada, com o pedido de trabalho e um item dentro."""
    command = Command.objects.create(account=account, restaurant=restaurant, branch=branch)
    if table is not None:
        command.current_table = table
        command.save(update_fields=["current_table"])
    order = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND,
        command=command, user=user,
    )
    item = add_order_item(order=order, product=product, quantity=quantity, user=user)
    order.refresh_from_db()
    command.refresh_from_db()
    return command, order, item


@pytest.fixture
def mesa_da_familia(account, restaurant, branch, manager_user, produto, mesa):
    """Três comandas na mesma mesa, cada uma com um item."""
    return [
        abrir_comanda_com_item(
            account=account, restaurant=restaurant, branch=branch,
            user=manager_user, product=produto, table=mesa,
        )
        for _ in range(3)
    ]
