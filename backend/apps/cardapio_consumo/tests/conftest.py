import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.cardapio_consumo.models import CardapioConsumo, ItemCardapioConsumo
from apps.core.tenant import tenant_context
from apps.menu.models import Ingredient, Product, Recipe, RecipeItem
from apps.stock.lots import post_stock_entry
from apps.stock.models import StockEntry, StockEntryItem, StockLocation


@pytest.fixture(autouse=True)
def _tenant(account):
    account.enabled_modules = ["logistica"]
    account.save(update_fields=["enabled_modules"])
    with tenant_context(account):
        yield


@pytest.fixture
def comum(account, restaurant, branch, manager_user):
    return {"account": account, "restaurant": restaurant, "branch": branch,
            "created_by": manager_user, "updated_by": manager_user}


@pytest.fixture
def cozinha(comum):
    return StockLocation.objects.create(**comum, name="Cozinha")


@pytest.fixture
def insumo(comum):
    def criar(nome, unidade="kg"):
        return Ingredient.objects.create(**comum, name=nome, unit=unidade)
    return criar


@pytest.fixture
def estoque(comum, cozinha, manager_user):
    """Dá entrada de `quantidade` (na unidade do insumo) no local."""
    def entrada(ingredient, quantidade, local=None):
        doc = StockEntry.objects.create(**comum, location=local or cozinha, effective_date=timezone.localdate())
        StockEntryItem.objects.create(**comum, entry=doc, ingredient=ingredient,
                                      package_quantity=Decimal(str(quantidade)), content_per_package=Decimal("1"),
                                      content_unit=ingredient.unit, unit_cost=Decimal("2"))
        post_stock_entry(entry=doc, user=manager_user)
    return entrada


@pytest.fixture
def produto_com_ficha(comum):
    def criar(nome, rendimento, componentes):
        produto = Product.objects.create(**comum, name=nome, internal_code=f"P{uuid.uuid4().hex[:6]}",
                                         sale_price=Decimal("10"))
        ficha = Recipe.objects.create(**comum, product=produto, yield_quantity=Decimal(str(rendimento)))
        for ingredient, quantidade, unidade in componentes:
            RecipeItem.objects.create(**comum, recipe=ficha, ingredient=ingredient,
                                      quantity=Decimal(str(quantidade)), unit=unidade)
        return produto
    return criar


@pytest.fixture
def cardapio(comum, cozinha):
    def criar(itens, **campos):
        campos.setdefault("comeca_em", date(2026, 1, 1))
        campos.setdefault("horario", time(6, 0))
        novo = CardapioConsumo.objects.create(**comum, nome=campos.pop("nome", "Buffet"), local=cozinha, **campos)
        for alvo, quantidade, *unidade in itens:
            chave = "ingredient" if isinstance(alvo, Ingredient) else "product"
            ItemCardapioConsumo.objects.create(**comum, cardapio=novo, quantidade=Decimal(str(quantidade)),
                                               unidade=unidade[0] if unidade else "", **{chave: alvo})
        return novo
    return criar
