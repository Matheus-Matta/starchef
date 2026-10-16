"""Fixtures da Balança Rápida: uma balança de comanda e as comandas 1, 2 e 3."""
import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.printers.models import Printer, Scale
from apps.restaurants.models import Command, TableSector


@pytest.fixture
def balanca(account, restaurant, branch):
    with tenant_context(account):
        categoria = ProductCategory.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Self-service"
        )
        produto = Product.objects.create(
            account=account, restaurant=restaurant, branch=branch, category=categoria,
            name="Prato por quilo", internal_code=f"K{uuid.uuid4().hex[:6]}",
            sale_price=Decimal("59.90"), pricing_unit=Product.PRICING_KG,
        )
        setor = TableSector.objects.create(account=account, restaurant=restaurant, branch=branch, name="B")
        impressora = Printer.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="B1", sector=setor, is_active=True
        )
        yield Scale.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Buffet",
            product=produto, printer=impressora, weighing_mode=Scale.MODE_COMMAND,
        )


@pytest.fixture
def comandas(account, restaurant, branch):
    with tenant_context(account):
        return [
            Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=n)
            for n in (1, 2, 3)
        ]
