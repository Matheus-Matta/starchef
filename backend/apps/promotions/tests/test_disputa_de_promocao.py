"""Quem ganha quando mais de uma promoção alcança o mesmo produto.

Duas perguntas, e as duas têm resposta fixa neste projeto: entre TABELAS vence a
mais antiga (foi o que o restaurante prometeu primeiro, e voltar atrás numa
promessa antiga é o que o cliente lê como propaganda enganosa); dentro de UMA
tabela vence a de cima (é o único critério que o gerente confere de relance, sem
simular).

Aqui também mora o silêncio: tabela fora da janela, desligada, ou de outra loja
não desconta nada.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

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
def test_fora_da_janela_a_tabela_nao_vale(tenant, account, restaurant, branch, categoria):
    produto = _produto(account, restaurant, branch, categoria, preco="20.00")
    ontem = timezone.now() - timedelta(days=2)
    tabela = _tabela(account, starts_at=ontem, ends_at=ontem + timedelta(hours=1))
    regra = _regra(account, tabela, discount_kind=Promotion.KIND_FIXED, discount_value=Decimal("9.90"))
    PromotionProduct.objects.create(account=account, promotion=regra, product=produto)

    assert tabela.is_active is False
    assert Product.objects.get(pk=produto.pk).current_price == Decimal("20.00")



@pytest.mark.django_db
def test_tabela_desligada_nao_vale_mesmo_dentro_da_janela(tenant, account, restaurant, branch, categoria):
    produto = _produto(account, restaurant, branch, categoria, preco="20.00")
    tabela = _tabela(account, is_enabled=False)
    regra = _regra(account, tabela, discount_kind=Promotion.KIND_FIXED, discount_value=Decimal("5.00"))
    PromotionProduct.objects.create(account=account, promotion=regra, product=produto)

    assert tabela.status_label == "Desligada"
    assert Product.objects.get(pk=produto.pk).current_price == Decimal("20.00")



@pytest.mark.django_db
def test_entre_tabelas_a_mais_antiga_ganha(tenant, account, restaurant, branch, categoria):
    """Duas tabelas alcançam o produto: vale a que foi prometida primeiro."""
    produto = _produto(account, restaurant, branch, categoria, preco="20.00")
    antiga = _tabela(account)
    nova = _tabela(account)
    # A ordem de criação é a ordem da disputa; forçamos a diferença de tempo
    # para o teste não depender da resolução do relógio.
    DiscountTable.all_objects.filter(pk=antiga.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )

    r1 = _regra(account, antiga, name="Antiga", discount_kind=Promotion.KIND_FIXED, discount_value=Decimal("12.00"))
    r2 = _regra(account, nova, name="Nova", discount_kind=Promotion.KIND_FIXED, discount_value=Decimal("8.00"))
    PromotionProduct.objects.create(account=account, promotion=r1, product=produto)
    PromotionProduct.objects.create(account=account, promotion=r2, product=produto)

    produto = Product.objects.get(pk=produto.pk)
    assert produto.current_price == Decimal("12.00")
    assert produto.active_promotion.promotion_name == "Antiga"



@pytest.mark.django_db
def test_na_mesma_tabela_o_topo_ganha(tenant, account, restaurant, branch, categoria):
    """Posição 1 vence posição 2 — mesmo que a 2 desconte mais.

    Prioridade legível na tela vale mais do que "o maior desconto": quem
    cadastrou consegue conferir a ordem de cima para baixo, e não simulando.
    """
    produto = _produto(account, restaurant, branch, categoria, preco="20.00")
    tabela = _tabela(account)
    topo = _regra(account, tabela, name="Topo", position=1,
                  target_type=Promotion.TARGET_CATEGORIES,
                  discount_kind=Promotion.KIND_PERCENT, discount_value=Decimal("10"))
    fundo = _regra(account, tabela, name="Fundo", position=2,
                   target_type=Promotion.TARGET_CATEGORIES,
                   discount_kind=Promotion.KIND_PERCENT, discount_value=Decimal("50"))
    topo.categories.add(categoria)
    fundo.categories.add(categoria)

    produto = Product.objects.get(pk=produto.pk)
    assert produto.current_price == Decimal("18.00")
    assert produto.active_promotion.promotion_name == "Topo"



@pytest.mark.django_db
def test_promocao_de_outra_loja_nao_desconta_aqui(tenant, account, restaurant, branch, categoria):
    from apps.promotions.pricing import ofertas_para
    from apps.restaurants.models import Restaurant

    outra = Restaurant.objects.create(
        account=account, trade_name="Outra loja", legal_name="Outra loja ME",
        cnpj=f"{uuid.uuid4().int % 10**14:014d}",
    )
    produto = _produto(account, restaurant, branch, categoria, preco="20.00")
    tabela = _tabela(account, restaurant=outra)
    regra = _regra(account, tabela, discount_kind=Promotion.KIND_FIXED, discount_value=Decimal("5.00"))
    PromotionProduct.objects.create(account=account, promotion=regra, product=produto)

    assert ofertas_para([produto], restaurant_id=restaurant.id) == {}
    # Sem restaurante informado (admin da conta), a promoção aparece: é o
    # cadastro querendo ver o que existe, não o caixa cobrando.
    assert ofertas_para([produto], restaurant_id=None)[produto.pk].price == Decimal("5.00")


