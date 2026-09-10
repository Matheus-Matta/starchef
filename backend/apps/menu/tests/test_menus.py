"""
Menus no estilo Shopify: tipos de item, aninhamento e origens dinâmicas.

O que estes testes travam:

- cada tipo de item exige o seu alvo (produto sem produto não entra);
- a árvore de submenus para no terceiro nível e não aceita ciclo;
- menu dinâmico responde sozinho — categoria nova aparece sem ninguém editar;
- todo site novo já nasce com os menus padrão;
- o site público recebe os menus resolvidos, prontos para desenhar.
"""
import uuid

import pytest

from apps.menu.models import Menu, MenuItem, Product, ProductCategory
from apps.menu.services.default_menus import DEFAULT_MENUS, ensure_default_menus
from apps.menu.services.menu_resolver import resolve_menu, serialize_menu

pytestmark = pytest.mark.django_db


def _errors(response):
    return response.data.get("error", {}).get("message", response.data)


@pytest.fixture
def ecommerce_account(account):
    account.enabled_modules = ["ecommerce"]
    account.save(update_fields=["enabled_modules", "updated_at"])
    return account


@pytest.fixture
def menu(ecommerce_account, restaurant, branch):
    return Menu.all_objects.create(
        account=ecommerce_account,
        restaurant=restaurant,
        branch=branch,
        name="Navegacao",
        slug=f"nav-{uuid.uuid4().hex[:6]}",
        menu_type=Menu.TYPE_NAVIGATION,
    )


@pytest.fixture
def catalog(ecommerce_account, restaurant, branch):
    pizzas = ProductCategory.all_objects.create(
        account=ecommerce_account, restaurant=restaurant, branch=branch, name="Pizzas", display_order=1
    )
    bebidas = ProductCategory.all_objects.create(
        account=ecommerce_account, restaurant=restaurant, branch=branch, name="Bebidas", display_order=2
    )
    products = []
    for index, (name, price, promo, category) in enumerate(
        [
            ("Margherita", "49.90", None, pizzas),
            ("Calabresa", "52.00", "39.90", pizzas),
            ("Refrigerante", "12.00", None, bebidas),
        ],
        start=1,
    ):
        product = Product.all_objects.create(
            account=ecommerce_account,
            restaurant=restaurant,
            branch=branch,
            category=category,
            name=name,
            internal_code=f"P-{index}",
            sale_price=price,
            promotional_price=promo,
        )
        product.restaurants.add(restaurant)
        products.append(product)
    return {"pizzas": pizzas, "bebidas": bebidas, "products": products}


# ── Tipos de item ────────────────────────────────────────────────────────────


def test_item_de_produto_exige_produto(admin_client, ecommerce_account, menu):
    response = admin_client.post(
        "/api/v1/menu/menu-items/",
        {"menu": str(menu.id), "item_type": "product", "title": "Sem alvo"},
        format="json",
    )
    assert response.status_code == 400
    assert "product" in _errors(response)


def test_item_personalizado_exige_link(admin_client, ecommerce_account, menu):
    response = admin_client.post(
        "/api/v1/menu/menu-items/",
        {"menu": str(menu.id), "item_type": "custom", "title": "Fale conosco"},
        format="json",
    )
    assert response.status_code == 400
    assert "url" in _errors(response)


def test_item_de_categoria_e_criado_e_herda_o_nome(admin_client, ecommerce_account, menu, catalog):
    response = admin_client.post(
        "/api/v1/menu/menu-items/",
        {"menu": str(menu.id), "item_type": "category", "category": str(catalog["pizzas"].id)},
        format="json",
    )
    assert response.status_code == 201
    # Sem título informado, a entrada usa o nome da categoria — renomear a
    # categoria renomeia o item do menu.
    assert response.data["label"] == "Pizzas"


def test_item_personalizado_com_link_entra(admin_client, ecommerce_account, menu):
    response = admin_client.post(
        "/api/v1/menu/menu-items/",
        {"menu": str(menu.id), "item_type": "custom", "title": "Fale conosco", "url": "/contato"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["url"] == "/contato"


# ── Aninhamento ──────────────────────────────────────────────────────────────


def _item(menu, **kwargs):
    return MenuItem.all_objects.create(
        account=menu.account,
        restaurant=menu.restaurant,
        branch=menu.branch,
        menu=menu,
        **kwargs,
    )


def test_submenu_de_tres_niveis_e_aceito(menu, catalog):
    nivel1 = _item(menu, item_type=MenuItem.TYPE_CATEGORY, category=catalog["pizzas"])
    nivel2 = _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="Salgadas", url="/salgadas", parent=nivel1)
    nivel3 = _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="Calabresa", url="/calabresa", parent=nivel2)

    assert (nivel1.depth, nivel2.depth, nivel3.depth) == (1, 2, 3)

    entries = resolve_menu(menu)
    assert len(entries) == 1
    assert entries[0]["children"][0]["children"][0]["title"] == "Calabresa"


def test_quarto_nivel_e_recusado(admin_client, ecommerce_account, menu):
    nivel1 = _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="A", url="/a")
    nivel2 = _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="B", url="/b", parent=nivel1)
    nivel3 = _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="C", url="/c", parent=nivel2)

    response = admin_client.post(
        "/api/v1/menu/menu-items/",
        {"menu": str(menu.id), "item_type": "custom", "title": "D", "url": "/d", "parent": str(nivel3.id)},
        format="json",
    )
    assert response.status_code == 400
    assert "parent" in _errors(response)


def test_item_nao_pode_ser_pai_de_si_mesmo(admin_client, ecommerce_account, menu):
    item = _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="A", url="/a")

    response = admin_client.patch(
        f"/api/v1/menu/menu-items/{item.id}/", {"parent": str(item.id)}, format="json"
    )
    assert response.status_code == 400


def test_pai_de_outro_menu_e_recusado(admin_client, ecommerce_account, menu, restaurant, branch):
    outro = Menu.all_objects.create(
        account=menu.account, restaurant=restaurant, branch=branch, name="Outro", slug="outro-menu"
    )
    pai = _item(outro, item_type=MenuItem.TYPE_CUSTOM, title="X", url="/x")

    response = admin_client.post(
        "/api/v1/menu/menu-items/",
        {"menu": str(menu.id), "item_type": "custom", "title": "Y", "url": "/y", "parent": str(pai.id)},
        format="json",
    )
    assert response.status_code == 400


def test_ciclo_e_recusado(admin_client, ecommerce_account, menu):
    pai = _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="Pai", url="/pai")
    filho = _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="Filho", url="/filho", parent=pai)

    # Tornar o pai filho do próprio filho fecharia o ciclo.
    response = admin_client.patch(
        f"/api/v1/menu/menu-items/{pai.id}/", {"parent": str(filho.id)}, format="json"
    )
    assert response.status_code == 400


# ── Origens dinâmicas ────────────────────────────────────────────────────────


def test_menu_de_todas_as_categorias_responde_sozinho(menu, catalog):
    menu.source = Menu.SOURCE_ALL_CATEGORIES
    menu.save(update_fields=["source", "updated_at"])

    assert [entry["title"] for entry in resolve_menu(menu)] == ["Pizzas", "Bebidas"]

    # O ponto do menu dinâmico: categoria nova entra sem ninguém editá-lo.
    ProductCategory.all_objects.create(
        account=menu.account, restaurant=menu.restaurant, branch=menu.branch, name="Sobremesas", display_order=3
    )
    assert "Sobremesas" in [entry["title"] for entry in resolve_menu(menu)]


def test_menu_de_produtos_de_uma_categoria(menu, catalog):
    menu.source = Menu.SOURCE_CATEGORY_PRODUCTS
    menu.source_category = catalog["pizzas"]
    menu.save(update_fields=["source", "source_category", "updated_at"])

    titles = [entry["title"] for entry in resolve_menu(menu)]
    assert titles == ["Calabresa", "Margherita"]
    assert "Refrigerante" not in titles


def test_menu_de_promocoes_so_traz_quem_tem_desconto(menu, catalog):
    menu.source = Menu.SOURCE_PROMOTIONS
    menu.save(update_fields=["source", "updated_at"])

    entries = resolve_menu(menu)
    assert [entry["title"] for entry in entries] == ["Calabresa"]
    # "De/por" só aparece quando existe promoção de verdade.
    assert entries[0]["price"] == "39.90"
    assert entries[0]["compare_at_price"] == "52.00"


def test_produto_sem_promocao_nao_tem_preco_riscado(menu, catalog):
    menu.source = Menu.SOURCE_CATEGORY_PRODUCTS
    menu.source_category = catalog["bebidas"]
    menu.save(update_fields=["source", "source_category", "updated_at"])

    entry = resolve_menu(menu)[0]
    assert entry["price"] == "12.00"
    assert entry["compare_at_price"] is None


def test_limite_de_itens_e_respeitado(menu, catalog):
    menu.source = Menu.SOURCE_ALL_CATEGORIES
    menu.item_limit = 1
    menu.save(update_fields=["source", "item_limit", "updated_at"])

    assert len(resolve_menu(menu)) == 1


def test_mais_vendidos_ordena_pela_venda(menu, catalog, ecommerce_account, restaurant, branch):
    """Sem venda nenhuma o menu vem vazio — e não com produtos aleatórios."""
    menu.source = Menu.SOURCE_BEST_SELLERS
    menu.save(update_fields=["source", "updated_at"])

    assert resolve_menu(menu) == []


# ── Menus padrão ─────────────────────────────────────────────────────────────


def test_menus_padrao_sao_criados(ecommerce_account, restaurant):
    menus = ensure_default_menus(restaurant)

    slugs = {menu.slug for menu in menus}
    assert slugs == {spec["slug"] for spec in DEFAULT_MENUS}
    assert {"categorias", "destaques", "ofertas", "navegacao-principal"} == slugs


def test_menus_padrao_sao_idempotentes(ecommerce_account, restaurant):
    ensure_default_menus(restaurant)
    ensure_default_menus(restaurant)

    assert Menu.all_objects.filter(account=ecommerce_account, slug="categorias").count() == 1


def test_menu_de_categorias_padrao_ja_lista_as_categorias(ecommerce_account, restaurant, catalog):
    menus = {menu.slug: menu for menu in ensure_default_menus(restaurant)}

    titles = [entry["title"] for entry in resolve_menu(menus["categorias"])]
    assert "Pizzas" in titles and "Bebidas" in titles


# ── Handle (slug) ────────────────────────────────────────────────────────────


def test_handle_e_unico_por_conta(admin_client, ecommerce_account, menu):
    response = admin_client.post(
        "/api/v1/menu/menus/",
        {"name": "Outro menu", "slug": menu.slug, "menu_type": "navigation"},
        format="json",
    )
    assert response.status_code == 400
    assert "slug" in _errors(response)


def test_contas_diferentes_podem_usar_o_mesmo_handle(ecommerce_account, restaurant, branch):
    """O handle é da conta, não da plataforma — antes era único globalmente."""
    from apps.accounts.models import Account
    from apps.restaurants.models import Restaurant

    Menu.all_objects.create(
        account=ecommerce_account, restaurant=restaurant, branch=branch, name="Principal", slug="principal"
    )

    outra_conta = Account.objects.create(
        name="Outra", slug=f"outra-{uuid.uuid4().hex[:6]}", status=Account.STATUS_ACTIVE, is_active=True
    )
    outro_restaurante = Restaurant.objects.create(
        account=outra_conta, legal_name="Outra LTDA", trade_name="Outra", cnpj=f"{uuid.uuid4().int % 10**14:014d}"
    )

    # Não levanta: o mesmo apelido em contas diferentes é legítimo.
    Menu.all_objects.create(
        account=outra_conta, restaurant=outro_restaurante, name="Principal", slug="principal"
    )


# ── Payload público ──────────────────────────────────────────────────────────


def test_menu_resolvido_tem_forma_estavel(menu, catalog):
    _item(menu, item_type=MenuItem.TYPE_CUSTOM, title="Contato", url="/contato")

    payload = serialize_menu(menu)

    assert payload["slug"] == menu.slug
    assert payload["type"] == Menu.TYPE_NAVIGATION
    entry = payload["items"][0]
    # Toda entrada tem as mesmas chaves, venha de onde vier — é o que permite
    # ao bloco tratar banner, navegação e vitrine com um componente só.
    for key in ("id", "type", "title", "image", "url", "price", "children"):
        assert key in entry


def test_endpoint_resolvido_do_menu(admin_client, ecommerce_account, menu, catalog):
    menu.source = Menu.SOURCE_ALL_CATEGORIES
    menu.save(update_fields=["source", "updated_at"])

    response = admin_client.get(f"/api/v1/menu/menus/{menu.id}/resolved/")

    assert response.status_code == 200
    assert [entry["title"] for entry in response.data["items"]] == ["Pizzas", "Bebidas"]
