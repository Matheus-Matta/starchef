"""
Montagem do payload público consolidado do storefront.

Uma requisição, uma resposta: o site precisa de restaurante, tema, página,
categorias, produtos, adicionais, horários, entrega e formas de pagamento
para pintar a primeira tela. Fatiar isso em seis endpoints faria o cardápio
abrir em seis idas ao servidor — no 4G do cliente, isso é a diferença entre
o pedido acontecer e não acontecer.

Duas regras valem aqui:

- **só o necessário e só o público.** Custo, margem, código interno, insumo,
  ficha técnica e qualquer campo fiscal ficam de fora. O que sai daqui é
  visível para o mundo, sem autenticação.
- **sem N+1.** Categorias, produtos, variações e adicionais são carregados em
  poucas queries; o resto é montado em memória. Um cardápio de 300 itens não
  pode virar 900 consultas.
"""
from decimal import Decimal

from django.db.models import Prefetch, Q

from apps.menu.models import Menu, Product, ProductAddon, ProductCategory, ProductVariation
from apps.menu.services.menu_resolver import serialize_menu
from apps.payments.models import PaymentMethod
from apps.restaurants.models import Branch, DeliveryZone
from apps.storefront.models import MenuPage


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
    except ValueError:
        return ""
    if request is None or url.startswith(("http://", "https://")):
        return url
    return request.build_absolute_uri(url)


def _serialize_product(product, request):
    primary = product.logo_image
    image_url = primary.public_url(request) if primary else _absolute(request, product.image)
    return {
        "id": str(product.id),
        "name": product.name,
        "description": product.description,
        "category_id": str(product.category_id) if product.category_id else None,
        "image": image_url,
        "logo_p": image_url,
        "photo_list": [
            {
                "id": str(link.image_id),
                "url": link.image.public_url(request),
                "is_primary": link.image_id == product.logo_image_id,
                "position": link.position,
            }
            for link in product.product_images.all()
        ],
        "price": _money(product.sale_price),
        "promotional_price": _money(product.promotional_price),
        "current_price": _money(product.current_price),
        "pricing_unit": product.pricing_unit,
        "is_weighed": product.is_weighed,
        "product_type": product.product_type,
        "preparation_minutes": product.average_preparation_time,
        "allows_addons": product.allows_addons,
        "allows_notes": product.allows_notes,
        "requires_variation": product.requires_variation,
        "available_for_delivery": product.available_for_delivery,
        "available_for_counter": product.available_for_counter,
        "variations": [
            {
                "id": str(variation.id),
                "name": variation.name,
                "price_delta": _money(variation.price_delta),
                "logo_p": variation.logo_image.public_url(request)
                if variation.logo_image
                else "",
            }
            for variation in product.variations.all()
            if variation.is_active and variation.deleted_at is None
        ],
        "addon_ids": [str(addon.id) for addon in product.addons.all() if addon.is_active and addon.deleted_at is None],
    }


def _page_dict(page):
    return {
        "id": str(page.id),
        "title": page.title,
        "slug": page.slug,
        "is_home": page.is_home,
        "seo": page.seo or {},
        "published_at": page.published_at.isoformat() if page.published_at else None,
        "data": page.published_data or {},
    }


def build_public_payload(site, *, page_slug=None, request=None):
    """Payload completo do site publicado. Devolve ``None`` se nada está no ar."""
    restaurant = site.restaurant
    account_id = site.account_id

    published_pages = list(
        MenuPage.all_objects.filter(
            site=site,
            status=MenuPage.STATUS_PUBLISHED,
            deleted_at__isnull=True,
        ).order_by("display_order", "title")
    )
    # Uma página com `published_data` vazio está marcada como publicada mas não
    # tem nada para mostrar — não entra na navegação do site.
    published_pages = [page for page in published_pages if page.published_data]

    current = None
    if page_slug:
        current = next((page for page in published_pages if page.slug == page_slug), None)
    if current is None:
        current = next((page for page in published_pages if page.is_home), None)
    if current is None and published_pages:
        current = published_pages[0]

    categories = [
        {
            "id": str(category.id),
            "name": category.name,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "display_order": category.display_order,
            "logo_url": category.logo_image.public_url(request) if category.logo_image else "",
        }
        for category in ProductCategory.all_objects.filter(
            account_id=account_id,
            is_active=True,
            deleted_at__isnull=True,
        )
        .filter(Q(restaurant=restaurant) | Q(restaurant__isnull=True))
        .select_related("logo_image")
        .order_by("display_order", "name")
    ]

    products_queryset = (
        Product.all_objects.filter(
            account_id=account_id,
            restaurants=restaurant,
            is_active=True,
            deleted_at__isnull=True,
        )
        .select_related("category", "logo_image")
        .prefetch_related(
            Prefetch(
                "variations",
                queryset=ProductVariation.all_objects.filter(deleted_at__isnull=True).select_related("logo_image"),
            ),
            Prefetch("addons", queryset=ProductAddon.all_objects.filter(deleted_at__isnull=True)),
            "product_images__image",
        )
        .order_by("category__display_order", "name")
        .distinct()
    )
    # Catálogo curado: quando o site aponta para um `menu.Menu`, só os produtos
    # daquele cardápio vão ao ar. É como o restaurante mostra um recorte
    # (ex.: só o que sai para delivery) sem mexer no cadastro de produtos.
    if site.catalog_id:
        products_queryset = products_queryset.filter(
            menu_items__menu_id=site.catalog_id,
            menu_items__is_active=True,
            menu_items__deleted_at__isnull=True,
        ).distinct()

    products = [_serialize_product(product, request) for product in products_queryset]

    addons = [
        {
            "id": str(addon.id),
            "name": addon.name,
            "price": _money(addon.price),
        }
        for addon in ProductAddon.all_objects.filter(
            account_id=account_id,
            is_active=True,
            deleted_at__isnull=True,
        )
        .filter(Q(restaurant=restaurant) | Q(restaurant__isnull=True))
        .order_by("name")
    ]

    branches = list(
        Branch.all_objects.filter(restaurant=restaurant, is_active=True, deleted_at__isnull=True).order_by("created_at")
    )
    branch_ids = [branch.id for branch in branches]

    opening_hours = [
        {
            "branch_id": str(branch.id),
            "branch_name": branch.name,
            "hours": branch.opening_hours or {},
        }
        for branch in branches
    ]

    delivery_zones = [
        {
            "id": str(zone.id),
            "name": zone.name,
            "min_radius_km": str(zone.min_radius_km),
            "max_radius_km": str(zone.max_radius_km),
            "delivery_fee": _money(zone.delivery_fee),
            "estimated_minutes": zone.estimated_minutes,
        }
        for zone in DeliveryZone.all_objects.filter(
            account_id=account_id, restaurant=restaurant, is_active=True, deleted_at__isnull=True
        ).order_by("min_radius_km")
    ]

    payment_methods = [
        {"id": str(method.id), "name": method.name, "method_type": method.method_type}
        for method in PaymentMethod.all_objects.filter(
            account_id=account_id, restaurant=restaurant, is_active=True, deleted_at__isnull=True
        ).order_by("name")
    ]

    # Menus resolvidos: e por eles que os blocos sabem o que mostrar no
    # carrossel de banners, na barra de navegacao e nas vitrines. Vao pelo
    # `slug` E pelo id, porque o bloco guarda um dos dois.
    menus = {
        menu.slug: serialize_menu(menu, request=request)
        for menu in Menu.all_objects.filter(
            account_id=account_id,
            restaurant=restaurant,
            is_active=True,
            deleted_at__isnull=True,
        )
        .select_related("source_category")
        .prefetch_related("items__product", "items__category")
        .order_by("name")
    }

    contact_branch = branches[0] if branches else None

    return {
        "restaurant": {
            "id": str(restaurant.id),
            "name": restaurant.trade_name,
            "logo": restaurant.logo_image.public_url(request) if restaurant.logo_image else _absolute(request, restaurant.logo),
            "phone": restaurant.phone or (contact_branch.phone if contact_branch else ""),
            "email": restaurant.email or (contact_branch.email if contact_branch else ""),
            "address": {
                "street": restaurant.address,
                "district": restaurant.district,
                "city": restaurant.city,
                "state": restaurant.state,
                "zip_code": restaurant.zip_code,
            },
        },
        "site": {
            "id": str(site.id),
            "slug": site.slug,
            "name": site.name or restaurant.trade_name,
            "theme": site.theme or {},
            "seo": site.seo or {},
            # Cabeçalho do SITE: o renderer o desenha em todas as páginas, e
            # não a partir de um bloco que o editor possa ter removido.
            "header": site.header or {},
            "is_active": site.is_active,
        },
        "page": _page_dict(current) if current else None,
        "pages": [
            {"title": page.title, "slug": page.slug, "is_home": page.is_home}
            for page in published_pages
        ],
        "categories": categories,
        "products": products,
        "addons": addons,
        "promotions": [product for product in products if product["promotional_price"]],
        "opening_hours": opening_hours,
        "delivery": {
            "enabled": bool(delivery_zones),
            "zones": delivery_zones,
        },
        "payment_methods": payment_methods,
        "menus": menus,
        "branches": [
            {
                "id": str(branch.id),
                "name": branch.name,
                "phone": branch.phone,
                "address": branch.address,
                "district": branch.district,
                "city": branch.city,
                "state": branch.state,
                "zip_code": branch.zip_code,
            }
            for branch in branches
        ],
        "meta": {"branch_ids": [str(branch_id) for branch_id in branch_ids]},
    }
