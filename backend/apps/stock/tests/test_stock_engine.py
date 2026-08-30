"""Fase 0 do plano de estoque: as correcoes do motor de baixa.

Cada teste aqui corresponde a um defeito concreto que o motor antigo tinha —
rendimento ignorado, unidade nao convertida, adicional invisivel, baixa
repetida a cada chamada, custo medio contando a entrada duas vezes. Ver
`docs/IMPLEMENTACAO_ESTOQUE.md`, secoes 4, 15 e 27.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Ingredient, Product, ProductCategory, ProductAddon, Recipe, RecipeItem
from apps.menu.services import update_ingredient_average_cost
from apps.menu.units import IncompatibleUnitError, convert
from apps.orders.models import Order, OrderItem, OrderItemAddon
from apps.stock.models import StockMovement
from apps.orders.services import create_order
from apps.stock.services import deduct_order_stock, revert_order_stock

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant(account):
    """Os managers do StarChef sao escopados por conta (ver `TenantManager`).

    Sem contexto, toda consulta volta vazia — como acontece na API, onde o
    middleware resolve a conta antes da view rodar.
    """
    with tenant_context(account):
        yield


@pytest.fixture
def category(account, restaurant, branch, manager_user):
    return ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Lanches",
        created_by=manager_user, updated_by=manager_user,
    )


@pytest.fixture
def product(account, restaurant, branch, manager_user, category):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=category,
        name="X-Burger", internal_code="XB1", sale_price=Decimal("25.00"),
        created_by=manager_user, updated_by=manager_user,
    )


# ── helpers ─────────────────────────────────────────────────────────────────
def _ingredient(account, restaurant, branch, user, *, name, unit, cost="0"):
    return Ingredient.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name=name,
        unit=unit,
        average_cost=Decimal(cost),
        created_by=user,
        updated_by=user,
    )


def _order_with_item(account, restaurant, branch, user, product, quantity="1"):
    # Pelo servico real, para o pedido nascer com `sequence` e auditoria como
    # nasce na venda. O item vai direto ao modelo: `add_order_item` exige o
    # vinculo produto-restaurante, que nao e o assunto destes testes.
    order = create_order(
        restaurant=restaurant,
        order_type=Order.TYPE_COUNTER,
        user=user,
    )
    item = OrderItem.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        order=order,
        product=product,
        quantity=Decimal(quantity),
        unit_price=product.sale_price,
        total_price=product.sale_price * Decimal(quantity),
        created_by=user,
        updated_by=user,
    )
    return order, item


def _balance(ingredient):
    total = Decimal("0")
    for movement in StockMovement.objects.filter(ingredient=ingredient):
        total += movement.quantity
    return total


# ── conversao de unidades ───────────────────────────────────────────────────
def test_converte_entre_unidades_da_mesma_grandeza():
    assert convert(Decimal("0.03"), "kg", "g") == Decimal("30")
    assert convert(Decimal("1500"), "ml", "l") == Decimal("1.5")
    assert convert(Decimal("2"), "unit", "unit") == Decimal("2")


def test_recusa_conversao_entre_grandezas_diferentes():
    # Litro para grama depende da densidade; um fator generico daria um numero
    # plausivel e errado.
    with pytest.raises(IncompatibleUnitError):
        convert(Decimal("1"), "l", "g")


# ── rendimento da receita ───────────────────────────────────────────────────
def test_baixa_divide_pelo_rendimento_da_receita(account, restaurant, branch, manager_user, product):
    """Receita que rende 10 porcoes e usa 1.000 g: 3 porcoes gastam 300 g."""
    macarrao = _ingredient(account, restaurant, branch, manager_user, name="Macarrao", unit="g", cost="0.02")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("10"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=macarrao, quantity=Decimal("1000"), unit="g",
        ingredient_cost=Decimal("0.02"), created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product, quantity="3")

    deduct_order_stock(order=order, user=manager_user)

    assert _balance(macarrao) == Decimal("-300.000")


def test_baixa_converte_a_unidade_da_ficha_para_a_do_insumo(
    account, restaurant, branch, manager_user, product
):
    """Ficha escrita em kg, insumo cadastrado em g: 0,03 kg sao 30 g."""
    queijo = _ingredient(account, restaurant, branch, manager_user, name="Queijo", unit="g")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=queijo, quantity=Decimal("0.03"), unit="kg",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)

    deduct_order_stock(order=order, user=manager_user)

    assert _balance(queijo) == Decimal("-30.000")


def test_linha_com_unidade_incompativel_e_pulada_sem_derrubar_a_venda(
    account, restaurant, branch, manager_user, product
):
    """O pedido ja foi pago: um cadastro torto nao pode travar o fechamento."""
    agua = _ingredient(account, restaurant, branch, manager_user, name="Agua", unit="g")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=agua, quantity=Decimal("1"), unit="l",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)

    created = deduct_order_stock(order=order, user=manager_user)

    assert created == []
    assert _balance(agua) == Decimal("0")


# ── idempotencia ────────────────────────────────────────────────────────────
def test_segunda_chamada_nao_duplica_a_baixa(account, restaurant, branch, manager_user, product):
    """A baixa dispara no envio a cozinha (uma vez por lote) E no pagamento."""
    carne = _ingredient(account, restaurant, branch, manager_user, name="Carne", unit="g")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=carne, quantity=Decimal("150"), unit="g",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)

    first = deduct_order_stock(order=order, user=manager_user)
    second = deduct_order_stock(order=order, user=manager_user)
    third = deduct_order_stock(order=order, user=manager_user)

    assert len(first) == 1
    assert second == [] and third == []
    assert _balance(carne) == Decimal("-150.000")


# ── adicionais ──────────────────────────────────────────────────────────────
def test_adicional_consome_o_insumo_vinculado(account, restaurant, branch, manager_user, product):
    bacon = _ingredient(account, restaurant, branch, manager_user, name="Bacon", unit="g")
    addon = ProductAddon.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Bacon extra",
        price=Decimal("4.00"), ingredient=bacon, consumption_quantity=Decimal("30"),
        consumption_unit="g", created_by=manager_user, updated_by=manager_user,
    )
    order, item = _order_with_item(account, restaurant, branch, manager_user, product, quantity="2")
    OrderItemAddon.objects.create(
        account=account, restaurant=restaurant, branch=branch, item=item, addon=addon,
        quantity=Decimal("1"), unit_price=addon.price, total_price=addon.price,
        created_by=manager_user, updated_by=manager_user,
    )

    deduct_order_stock(order=order, user=manager_user)

    # 30 g por unidade x 1 adicional x 2 itens.
    assert _balance(bacon) == Decimal("-60.000")


def test_adicional_sem_insumo_vinculado_nao_baixa_nada(
    account, restaurant, branch, manager_user, product
):
    """Adicional legado, ainda so comercial: nao inventa consumo."""
    addon = ProductAddon.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Sem insumo",
        price=Decimal("2.00"), created_by=manager_user, updated_by=manager_user,
    )
    order, item = _order_with_item(account, restaurant, branch, manager_user, product)
    OrderItemAddon.objects.create(
        account=account, restaurant=restaurant, branch=branch, item=item, addon=addon,
        quantity=Decimal("1"), unit_price=addon.price, total_price=addon.price,
        created_by=manager_user, updated_by=manager_user,
    )

    assert deduct_order_stock(order=order, user=manager_user) == []


# ── produto direto ──────────────────────────────────────────────────────────
def test_produto_direto_sem_receita_baixa_o_insumo(
    account, restaurant, branch, manager_user, category
):
    lata = _ingredient(account, restaurant, branch, manager_user, name="Refri lata", unit="unit")
    refri = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=category,
        name="Refrigerante lata", internal_code="REF1", sale_price=Decimal("6.00"),
        controls_stock=True, stock_ingredient=lata,
        stock_consumption_quantity=Decimal("1"), stock_consumption_unit="unit",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, refri, quantity="3")

    deduct_order_stock(order=order, user=manager_user)

    assert _balance(lata) == Decimal("-3.000")


def test_produto_com_receita_ignora_o_vinculo_direto(
    account, restaurant, branch, manager_user, product
):
    """Ficha tecnica e vinculo direto juntos baixariam o mesmo saldo duas vezes."""
    insumo = _ingredient(account, restaurant, branch, manager_user, name="Insumo", unit="g")
    product.stock_ingredient = insumo
    product.stock_consumption_quantity = Decimal("500")
    product.stock_consumption_unit = "g"
    product.save(update_fields=["stock_ingredient", "stock_consumption_quantity", "stock_consumption_unit"])
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=insumo, quantity=Decimal("100"), unit="g",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)

    deduct_order_stock(order=order, user=manager_user)

    # So a receita: 100 g, e nao 100 + 500.
    assert _balance(insumo) == Decimal("-100.000")


# ── snapshot e reversao ─────────────────────────────────────────────────────
def test_mudar_a_receita_depois_nao_altera_a_baixa_ja_feita(
    account, restaurant, branch, manager_user, product
):
    farinha = _ingredient(account, restaurant, branch, manager_user, name="Farinha", unit="g")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    recipe_item = RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=farinha, quantity=Decimal("200"), unit="g",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)
    deduct_order_stock(order=order, user=manager_user)

    recipe_item.quantity = Decimal("900")
    recipe_item.save(update_fields=["quantity"])

    movement = StockMovement.objects.get(ingredient=farinha)
    assert movement.quantity == Decimal("-200.000")
    # A composicao congelada guarda o que valia na hora da venda, nao o que a
    # ficha passou a dizer depois.
    assert Decimal(movement.source_snapshot["quantity_per_yield"]) == Decimal("200")


def test_reversao_devolve_ao_estoque_sem_apagar_a_baixa(
    account, restaurant, branch, manager_user, product
):
    cebola = _ingredient(account, restaurant, branch, manager_user, name="Cebola", unit="g")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=cebola, quantity=Decimal("50"), unit="g",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)
    deduct_order_stock(order=order, user=manager_user)

    reversals = revert_order_stock(order=order, user=manager_user, reason="Pedido estornado")

    assert len(reversals) == 1
    assert _balance(cebola) == Decimal("0")
    # A baixa original continua no livro — o insumo chegou a sair.
    assert StockMovement.objects.filter(
        ingredient=cebola, movement_type=StockMovement.TYPE_SALE
    ).count() == 1


def test_reverter_duas_vezes_nao_devolve_em_dobro(
    account, restaurant, branch, manager_user, product
):
    alho = _ingredient(account, restaurant, branch, manager_user, name="Alho", unit="g")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=alho, quantity=Decimal("10"), unit="g",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)
    deduct_order_stock(order=order, user=manager_user)

    revert_order_stock(order=order, user=manager_user)
    second = revert_order_stock(order=order, user=manager_user)

    assert second == []
    assert _balance(alho) == Decimal("0")


# ── custo medio ─────────────────────────────────────────────────────────────
def test_custo_medio_nao_conta_a_entrada_duas_vezes(
    account, restaurant, branch, manager_user
):
    """10 un a R$ 1,00 ja em estoque + 10 un a R$ 3,00 = media R$ 2,00.

    Antes, o saldo lido ja incluia a entrada nova e ela era somada de novo:
    a ponderacao usava 20 unidades a chegar contra 20 em estoque e puxava a
    media para perto do custo da compra.
    """
    from apps.stock.models import StockLocation

    insumo = _ingredient(account, restaurant, branch, manager_user, name="Insumo", unit="unit", cost="1.00")
    location = StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Principal",
        created_by=manager_user, updated_by=manager_user,
    )
    base = dict(
        account=account, restaurant=restaurant, branch=branch, ingredient=insumo,
        location=location, operator=manager_user, movement_type=StockMovement.TYPE_IN,
        created_by=manager_user, updated_by=manager_user,
    )
    StockMovement.objects.create(quantity=Decimal("10"), unit_cost=Decimal("1.00"), **base)

    # A entrada nova ja esta gravada quando o recalculo roda (o viewset salva
    # o movimento e so entao chama o servico).
    StockMovement.objects.create(quantity=Decimal("10"), unit_cost=Decimal("3.00"), **base)
    update_ingredient_average_cost(insumo, Decimal("10"), Decimal("3.00"))

    insumo.refresh_from_db()
    assert insumo.average_cost == Decimal("2.0000")


def test_primeira_entrada_define_o_custo_medio(account, restaurant, branch, manager_user):
    from apps.stock.models import StockLocation

    insumo = _ingredient(account, restaurant, branch, manager_user, name="Novo", unit="unit")
    location = StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Principal",
        created_by=manager_user, updated_by=manager_user,
    )
    StockMovement.objects.create(
        account=account, restaurant=restaurant, branch=branch, ingredient=insumo,
        location=location, operator=manager_user, movement_type=StockMovement.TYPE_IN,
        quantity=Decimal("5"), unit_cost=Decimal("7.50"),
        created_by=manager_user, updated_by=manager_user,
    )
    update_ingredient_average_cost(insumo, Decimal("5"), Decimal("7.50"))

    insumo.refresh_from_db()
    assert insumo.average_cost == Decimal("7.5000")


def test_cada_item_do_pedido_baixa_o_proprio_consumo(
    account, restaurant, branch, manager_user, product, category
):
    """Dois itens no mesmo pedido: chaves distintas, baixas somadas."""
    massa = _ingredient(account, restaurant, branch, manager_user, name="Massa", unit="g")
    outro = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=category,
        name="Pizza", internal_code="PZ1", sale_price=Decimal("40.00"),
        created_by=manager_user, updated_by=manager_user,
    )
    for target, grams in ((product, "100"), (outro, "250")):
        recipe = Recipe.objects.create(
            account=account, restaurant=restaurant, branch=branch, product=target,
            yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
        )
        RecipeItem.objects.create(
            account=account, restaurant=restaurant, branch=branch, recipe=recipe,
            ingredient=massa, quantity=Decimal(grams), unit="g",
            created_by=manager_user, updated_by=manager_user,
        )

    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)
    OrderItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, order=order, product=outro,
        quantity=Decimal("1"), unit_price=outro.sale_price, total_price=outro.sale_price,
        created_by=manager_user, updated_by=manager_user,
    )

    created = deduct_order_stock(order=order, user=manager_user)

    assert len(created) == 2
    assert len({movement.source_key for movement in created}) == 2
    assert _balance(massa) == Decimal("-350.000")


def test_pedidos_diferentes_nao_colidem_na_chave_de_origem(
    account, restaurant, branch, manager_user, product
):
    """A chave e por ITEM: o mesmo produto em dois pedidos baixa duas vezes."""
    sal = _ingredient(account, restaurant, branch, manager_user, name="Sal", unit="g")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=sal, quantity=Decimal("5"), unit="g",
        created_by=manager_user, updated_by=manager_user,
    )

    for _ in range(2):
        order, _ = _order_with_item(account, restaurant, branch, manager_user, product)
        deduct_order_stock(order=order, user=manager_user)

    assert _balance(sal) == Decimal("-10.000")


def test_adicional_com_quantidade_maior_que_um(
    account, restaurant, branch, manager_user, product
):
    """Bacon duplo: 30 g x 2 adicionais x 1 item."""
    bacon = _ingredient(account, restaurant, branch, manager_user, name="Bacon", unit="g")
    addon = ProductAddon.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Bacon extra",
        price=Decimal("4.00"), ingredient=bacon, consumption_quantity=Decimal("30"),
        consumption_unit="g", created_by=manager_user, updated_by=manager_user,
    )
    order, item = _order_with_item(account, restaurant, branch, manager_user, product)
    OrderItemAddon.objects.create(
        account=account, restaurant=restaurant, branch=branch, item=item, addon=addon,
        quantity=Decimal("2"), unit_price=addon.price, total_price=addon.price * 2,
        created_by=manager_user, updated_by=manager_user,
    )

    deduct_order_stock(order=order, user=manager_user)

    assert _balance(bacon) == Decimal("-60.000")


def test_previa_do_consumo_nao_grava_movimento(
    account, restaurant, branch, manager_user, product
):
    """`order_stock_components` serve a tela: calcula sem baixar."""
    from apps.stock.services import order_stock_components

    oleo = _ingredient(account, restaurant, branch, manager_user, name="Oleo", unit="ml")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("4"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=oleo, quantity=Decimal("1"), unit="l",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product, quantity="2")

    components = list(order_stock_components(order))

    # 1 l = 1.000 ml, rendendo 4 porcoes, vendidas 2: 500 ml.
    assert len(components) == 1
    assert components[0].quantity == Decimal("500")
    assert StockMovement.objects.count() == 0
    assert _balance(oleo) == Decimal("0")


def test_reversao_nao_toca_em_movimento_manual(
    account, restaurant, branch, manager_user, product
):
    """Reverter a venda nao pode desfazer uma entrada de compra."""
    from apps.stock.models import StockLocation

    acucar = _ingredient(account, restaurant, branch, manager_user, name="Acucar", unit="g")
    location = StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Deposito",
        created_by=manager_user, updated_by=manager_user,
    )
    StockMovement.objects.create(
        account=account, restaurant=restaurant, branch=branch, ingredient=acucar,
        location=location, operator=manager_user, movement_type=StockMovement.TYPE_IN,
        quantity=Decimal("1000"), unit_cost=Decimal("0.01"),
        created_by=manager_user, updated_by=manager_user,
    )
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=acucar, quantity=Decimal("20"), unit="g",
        created_by=manager_user, updated_by=manager_user,
    )
    order, _ = _order_with_item(account, restaurant, branch, manager_user, product)
    deduct_order_stock(order=order, user=manager_user)

    reversals = revert_order_stock(order=order, user=manager_user)

    assert len(reversals) == 1
    assert reversals[0].reversal_of.movement_type == StockMovement.TYPE_SALE
    # A entrada de 1.000 g continua de pe.
    assert _balance(acucar) == Decimal("1000.000")


# ── validacao de cadastro ───────────────────────────────────────────────────
def test_cadastro_recusa_unidade_incompativel_no_adicional(
    account, restaurant, branch, manager_user
):
    """O erro precisa aparecer no cadastro: na venda ele passa em silencio."""
    from apps.menu.serializers import ProductAddonSerializer

    agua = _ingredient(account, restaurant, branch, manager_user, name="Agua", unit="g")
    serializer = ProductAddonSerializer(data={
        "restaurant": str(restaurant.id), "branch": str(branch.id), "name": "Dose",
        "price": "1.00", "ingredient": str(agua.id),
        "consumption_quantity": "1", "consumption_unit": "l",
    })

    assert not serializer.is_valid()
    assert "consumption_unit" in serializer.errors


def test_cadastro_recusa_insumo_sem_quantidade_de_consumo(
    account, restaurant, branch, manager_user
):
    from apps.menu.serializers import ProductAddonSerializer

    bacon = _ingredient(account, restaurant, branch, manager_user, name="Bacon", unit="g")
    serializer = ProductAddonSerializer(data={
        "restaurant": str(restaurant.id), "branch": str(branch.id), "name": "Bacon",
        "price": "4.00", "ingredient": str(bacon.id), "consumption_quantity": "0",
    })

    assert not serializer.is_valid()
    assert "consumption_quantity" in serializer.errors


def test_cadastro_aceita_adicional_sem_vinculo_de_insumo(restaurant, branch):
    """Adicional puramente comercial continua valido."""
    from apps.menu.serializers import ProductAddonSerializer

    serializer = ProductAddonSerializer(data={
        "restaurant": str(restaurant.id), "branch": str(branch.id),
        "name": "Sem insumo", "price": "2.00",
    })

    assert serializer.is_valid(), serializer.errors


def test_cadastro_recusa_quantidade_de_consumo_sem_insumo(restaurant, branch, category):
    """Quantidade preenchida sem dizer de qual insumo nao baixa nada."""
    from apps.menu.serializers import ProductSerializer

    serializer = ProductSerializer(data={
        "restaurant": str(restaurant.id), "branch": str(branch.id),
        "category": str(category.id), "name": "Refri", "internal_code": "RF9",
        "sale_price": "6.00", "stock_consumption_quantity": "1",
    })

    assert not serializer.is_valid()
    assert "stock_ingredient" in serializer.errors


def test_cadastro_recusa_unidade_incompativel_no_produto_direto(
    account, restaurant, branch, manager_user, category
):
    from apps.menu.serializers import ProductSerializer

    lata = _ingredient(account, restaurant, branch, manager_user, name="Lata", unit="unit")
    serializer = ProductSerializer(data={
        "restaurant": str(restaurant.id), "branch": str(branch.id),
        "category": str(category.id), "name": "Refri", "internal_code": "RF8",
        "sale_price": "6.00", "stock_ingredient": str(lata.id),
        "stock_consumption_quantity": "350", "stock_consumption_unit": "ml",
    })

    assert not serializer.is_valid()
    assert "stock_consumption_unit" in serializer.errors


def test_unidade_desconhecida_e_recusada():
    with pytest.raises(IncompatibleUnitError):
        convert(Decimal("1"), "duzia", "unit")


# ── item cancelado ──────────────────────────────────────────────────────────
def test_item_cancelado_nao_consome_insumo(account, restaurant, branch, manager_user, product):
    tomate = _ingredient(account, restaurant, branch, manager_user, name="Tomate", unit="g")
    recipe = Recipe.objects.create(
        account=account, restaurant=restaurant, branch=branch, product=product,
        yield_quantity=Decimal("1"), created_by=manager_user, updated_by=manager_user,
    )
    RecipeItem.objects.create(
        account=account, restaurant=restaurant, branch=branch, recipe=recipe,
        ingredient=tomate, quantity=Decimal("40"), unit="g",
        created_by=manager_user, updated_by=manager_user,
    )
    order, item = _order_with_item(account, restaurant, branch, manager_user, product)
    item.status = OrderItem.STATUS_CANCELLED
    item.save(update_fields=["status"])

    assert deduct_order_stock(order=order, user=manager_user) == []
    assert _balance(tomate) == Decimal("0")
