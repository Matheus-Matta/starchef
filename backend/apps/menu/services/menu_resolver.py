"""
Resolve um `Menu` na lista de entradas que o site vai desenhar.

Um menu tem duas naturezas, e este módulo é o lugar onde elas viram a mesma
coisa:

- **manual** — o restaurante escolheu item a item, na ordem que quis;
- **dinâmico** — o menu é uma *pergunta* ("todas as categorias", "os 5 mais
  vendidos"), respondida na hora de renderizar.

A diferença importa: um menu "todas as categorias" montado como lista fixa
ficaria desatualizado no dia em que o restaurante criasse uma categoria nova —
e ninguém lembraria de voltar aqui para incluí-la. Por isso o tipo dinâmico
existe: ele responde certo sem manutenção.

**Frescor dos menus dinâmicos.** O payload público é cacheado por restaurante
(ver `apps.storefront.services.cache`), e uma VENDA não derruba esse cache de
propósito: durante o serviço, cada item de pedido invalidaria o cardápio
inteiro e o cache deixaria de existir na hora em que ele mais importa. Um
"mais vendidos" com até o TTL do cache de atraso não incomoda ninguém —
publicar uma página ou mexer no menu, isso sim, invalida na hora.

A saída é sempre a mesma forma, venha de onde vier — é isso que permite ao
bloco do storefront tratar carrossel de banner, barra de navegação e vitrine
com um componente só:

    {
      "id": "...",           # id do item (vazio nas origens dinâmicas)
      "type": "product",     # product | category | image | custom
      "title": "Pizza Calabresa",
      "subtitle": "",
      "image": "https://…",
      "url": "/produto/…",
      "opens_in_new_tab": False,
      "product_id": "…", "category_id": None,
      "price": "39.90", "compare_at_price": "52.00",
      "children": [...],
    }
"""
from decimal import Decimal

from django.db.models import Q, Sum

from apps.menu.models import Menu, MenuItem, Product, ProductCategory

# Teto das origens dinâmicas quando o menu não define um. Um carrossel com 200
# produtos não é um carrossel — é um jeito de deixar a página lenta.
DEFAULT_DYNAMIC_LIMIT = 12


def _money(value):
    if value is None:
        return None
    return str(Decimal(value).quantize(Decimal("0.01")))


def _absolute(request, image):
    """URL absoluta da imagem — o site roda em outro domínio que o backend."""
    if not image:
        return ""
    try:
        url = image.url
    except (ValueError, AttributeError):
        return ""
    if not url or request is None or url.startswith(("http://", "https://")):
        return url
    return request.build_absolute_uri(url)


def _entry(**overrides):
    """Uma entrada com todas as chaves — o front nunca recebe forma variável."""
    entry = {
        "id": "",
        "type": MenuItem.TYPE_CUSTOM,
        "title": "",
        "subtitle": "",
        "image": "",
        "url": "",
        "opens_in_new_tab": False,
        "product_id": None,
        "category_id": None,
        "price": None,
        "compare_at_price": None,
        "children": [],
    }
    entry.update(overrides)
    return entry


def product_entry(product, *, request=None, item=None):
    """Produto → entrada. `item` traz o que o menu sobrescreve (título, foto, preço)."""
    price = item.override_price if item and item.override_price is not None else product.current_price
    # "De/por" só quando há promoção de verdade: um preço riscado igual ao
    # cobrado é propaganda enganosa, não desconto.
    compare_at = product.sale_price if product.promotional_price else None
    return _entry(
        id=str(item.id) if item else "",
        type=MenuItem.TYPE_PRODUCT,
        title=(item.title if item and item.title else product.name),
        subtitle=(item.subtitle if item else "") or product.description[:255],
        image=_absolute(
            request,
            item.image if item and item.image else (product.logo_image or product.image),
        ),
        url=(item.url if item and item.url else f"/produto/{product.id}"),
        opens_in_new_tab=bool(item.opens_in_new_tab) if item else False,
        product_id=str(product.id),
        category_id=str(product.category_id) if product.category_id else None,
        price=_money(price),
        compare_at_price=_money(compare_at),
    )


def category_entry(category, *, request=None, item=None):
    return _entry(
        id=str(item.id) if item else "",
        type=MenuItem.TYPE_CATEGORY,
        title=(item.title if item and item.title else category.name),
        subtitle=(item.subtitle if item else ""),
        image=_absolute(request, item.image if item and item.image else category.logo_image),
        url=(item.url if item and item.url else f"/categoria/{category.id}"),
        opens_in_new_tab=bool(item.opens_in_new_tab) if item else False,
        category_id=str(category.id),
    )


def item_entry(item, *, request=None):
    """Item cadastrado → entrada, seja qual for o tipo."""
    if item.item_type == MenuItem.TYPE_PRODUCT and item.product_id:
        entry = product_entry(item.product, request=request, item=item)
    elif item.item_type == MenuItem.TYPE_CATEGORY and item.category_id:
        entry = category_entry(item.category, request=request, item=item)
    else:
        entry = _entry(
            id=str(item.id),
            type=item.item_type,
            title=item.label,
            subtitle=item.subtitle,
            image=_absolute(request, item.image),
            url=item.url,
            opens_in_new_tab=item.opens_in_new_tab,
        )
    return entry


# ── Origens dinâmicas ────────────────────────────────────────────────────────


def _active_categories(menu):
    return (
        ProductCategory.all_objects.filter(
            account_id=menu.account_id, is_active=True, deleted_at__isnull=True, parent__isnull=True
        )
        .filter(Q(restaurant_id=menu.restaurant_id) | Q(restaurant__isnull=True))
        .select_related("logo_image")
        .order_by("display_order", "name")
    )


def _active_products(menu):
    return (
        Product.all_objects.filter(
            account_id=menu.account_id,
            restaurants=menu.restaurant_id,
            is_active=True,
            deleted_at__isnull=True,
        )
        .select_related("category", "logo_image")
        .distinct()
    )


def _best_selling_products(menu, limit):
    """Produtos mais vendidos, por quantidade somada nos itens de pedido.

    Importado aqui dentro de propósito: `apps.orders` já depende de
    `apps.menu`, e um import no topo fecharia o ciclo.
    """
    from apps.orders.models import OrderItem

    ranking = (
        OrderItem.all_objects.filter(
            account_id=menu.account_id,
            restaurant_id=menu.restaurant_id,
            deleted_at__isnull=True,
        )
        .exclude(status=OrderItem.STATUS_CANCELLED)
        .values("product_id")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[: limit or DEFAULT_DYNAMIC_LIMIT]
    )
    ordered_ids = [row["product_id"] for row in ranking]
    if not ordered_ids:
        return []

    products = {product.id: product for product in _active_products(menu).filter(id__in=ordered_ids)}
    # Reordena pela venda: o `filter(id__in=…)` volta na ordem do banco, e o
    # ponto de um "mais vendidos" é justamente a ordem.
    return [products[product_id] for product_id in ordered_ids if product_id in products]


def _dynamic_entries(menu, request):
    limit = menu.item_limit or DEFAULT_DYNAMIC_LIMIT

    if menu.source == Menu.SOURCE_ALL_CATEGORIES:
        categories = _active_categories(menu)
        if menu.item_limit:
            categories = categories[: menu.item_limit]
        return [category_entry(category, request=request) for category in categories]

    if menu.source == Menu.SOURCE_CATEGORY_PRODUCTS:
        if not menu.source_category_id:
            return []
        products = _active_products(menu).filter(category_id=menu.source_category_id).order_by("name")[:limit]
        return [product_entry(product, request=request) for product in products]

    if menu.source == Menu.SOURCE_BEST_SELLERS:
        return [product_entry(product, request=request) for product in _best_selling_products(menu, limit)]

    if menu.source == Menu.SOURCE_PROMOTIONS:
        products = (
            _active_products(menu)
            .filter(promotional_price__isnull=False)
            .order_by("category__display_order", "name")[:limit]
        )
        return [product_entry(product, request=request) for product in products]

    return []


# ── Entrada pública ──────────────────────────────────────────────────────────


def resolve_menu(menu, *, request=None):
    """Entradas de um menu, prontas para renderizar (árvore, com `children`)."""
    if menu.is_dynamic:
        return _dynamic_entries(menu, request)

    items = (
        MenuItem.all_objects.filter(menu=menu, is_active=True, deleted_at__isnull=True)
        .select_related("product", "product__logo_image", "category", "category__logo_image")
        .order_by("display_order", "created_at")
    )

    # Uma consulta só e a árvore montada em memória: buscar os filhos de cada
    # item daria uma consulta por linha do menu.
    entries = {}
    children_by_parent = {}
    for item in items:
        entries[item.id] = item_entry(item, request=request)
        children_by_parent.setdefault(item.parent_id, []).append(item.id)

    def build(parent_id, depth=1):
        if depth > MenuItem.MAX_DEPTH:
            return []
        result = []
        for item_id in children_by_parent.get(parent_id, []):
            entry = entries[item_id]
            entry["children"] = build(item_id, depth + 1)
            result.append(entry)
        return result

    return build(None)


def serialize_menu(menu, *, request=None):
    """O menu inteiro (identificação + entradas) para o payload público."""
    return {
        "id": str(menu.id),
        "slug": menu.slug,
        "name": menu.name,
        "type": menu.menu_type,
        "source": menu.source,
        "items": resolve_menu(menu, request=request),
    }
