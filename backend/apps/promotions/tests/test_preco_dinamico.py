"""O preço do produto sai de cálculo — e o cadastro nunca é tocado.

Estes testes fixam a promessa central do desenho: `base_price` é sagrado, e o
que muda é qual tabela de desconto alcança o produto neste instante. Se algum
dia alguém "otimizar" gravando o preço promocional na coluna, é aqui que
aparece.
"""

import uuid
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.promotions.models import DiscountTable, Promotion, PromotionProduct


@pytest.fixture
def tenant(account):
    with tenant_context(account):
        yield account


@pytest.fixture
def categoria(tenant, account, restaurant, branch):
    return ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Bebidas"
    )


def _produto(account, restaurant, branch, categoria, preco="20.00", promocional=None):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="Refrigerante", internal_code=f"R{uuid.uuid4().hex[:6]}",
        sale_price=Decimal(preco),
        promotional_price=Decimal(promocional) if promocional else None,
    )


def _tabela(account, restaurant=None, **campos):
    return DiscountTable.objects.create(
        account=account, restaurant=restaurant, name=f"Tabela {uuid.uuid4().hex[:6]}", **campos
    )


def _regra(account, tabela, **campos):
    campos.setdefault("name", "Regra")
    campos.setdefault("target_type", Promotion.TARGET_PRODUCTS)
    return Promotion.objects.create(account=account, table=tabela, **campos)


@pytest.mark.django_db
def test_sem_promocao_o_preco_e_o_cadastrado(tenant, account, restaurant, branch, categoria):
    produto = _produto(account, restaurant, branch, categoria, preco="20.00")
    assert produto.sale_price == Decimal("20.00")
    assert produto.promotional_price is None
    assert produto.current_price == Decimal("20.00")
    assert produto.compare_at_price is None



@pytest.mark.django_db
def test_o_nome_antigo_continua_gravando(tenant, account, restaurant, branch, categoria):
    """`sale_price=` no construtor e na atribuição seguem funcionando.

    É o que mantém semeadura, testes e desserialização do sync de pé depois da
    renomeação das colunas.
    """
    produto = _produto(account, restaurant, branch, categoria, preco="31.50")
    assert produto.base_price == Decimal("31.50")
    produto.sale_price = Decimal("42.00")
    produto.save(update_fields=["base_price"])
    produto.refresh_from_db()
    assert produto.base_price == Decimal("42.00")



@pytest.mark.django_db
def test_percentual_em_categoria_desconta_sobre_a_prateleira(tenant, account, restaurant, branch, categoria):
    """10% sobre um produto que já tem promocional manual desce sobre o MENOR.

    O contrário — descontar sobre o preço cheio — aumentaria o preço de quem já
    estava em promoção: 10% de 20 dá 18, e o produto estava a 15.
    """
    produto = _produto(account, restaurant, branch, categoria, preco="20.00", promocional="15.00")
    tabela = _tabela(account)
    regra = _regra(account, tabela, target_type=Promotion.TARGET_CATEGORIES,
                   discount_kind=Promotion.KIND_PERCENT, discount_value=Decimal("10"))
    regra.categories.add(categoria)

    produto = Product.objects.get(pk=produto.pk)
    assert produto.current_price == Decimal("13.50")
    assert produto.compare_at_price == Decimal("15.00")



@pytest.mark.django_db
def test_de_e_por_do_encarte_vencem_o_cadastro(tenant, account, restaurant, branch, categoria):
    """"De 30 por 15" num produto cadastrado a 20 — e o cadastro fica em 20.

    É o pedido literal: a tabela promocional altera o valor cheio EXIBIDO e o
    promocional, sem que o produto perca o preço que foi cadastrado.
    """
    produto = _produto(account, restaurant, branch, categoria, preco="20.00")
    tabela = _tabela(account)
    regra = _regra(account, tabela, discount_kind=Promotion.KIND_FIXED, discount_value=Decimal("0"))
    PromotionProduct.objects.create(
        account=account, promotion=regra, product=produto,
        promotional_price=Decimal("15.00"), compare_at_price=Decimal("30.00"),
    )

    produto = Product.objects.get(pk=produto.pk)
    assert produto.current_price == Decimal("15.00")
    assert produto.compare_at_price == Decimal("30.00")
    # O cadastro permanece intacto — a promoção não escreve no produto.
    assert produto.base_price == Decimal("20.00")



@pytest.mark.django_db
def test_desconto_nao_leva_o_preco_a_negativo(tenant, account, restaurant, branch, categoria):
    produto = _produto(account, restaurant, branch, categoria, preco="20.00")
    tabela = _tabela(account)
    regra = _regra(account, tabela, discount_kind=Promotion.KIND_AMOUNT, discount_value=Decimal("50.00"))
    PromotionProduct.objects.create(account=account, promotion=regra, product=produto)

    assert Product.objects.get(pk=produto.pk).current_price == Decimal("0.00")
