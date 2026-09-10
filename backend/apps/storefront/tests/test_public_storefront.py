"""Endpoint público, resolução por domínio e invalidação de cache."""
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.storefront.models import MenuDomain, MenuPage
from apps.storefront.services import cache as storefront_cache
from apps.storefront.services import domains as domain_service
from apps.storefront.tests.conftest import SIMPLE_PROJECT

pytestmark = pytest.mark.django_db


@pytest.fixture
def published_page(page, catalog):
    from apps.storefront.services.publishing import publish_page

    return publish_page(page)


@pytest.fixture
def public_client():
    """Cliente sem autenticação — é assim que o cliente final chega no site."""
    return APIClient()


# ── Payload público ──────────────────────────────────────────────────────────


def test_endpoint_publico_devolve_tudo_que_o_site_precisa(public_client, site, published_page, catalog):
    response = public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    assert response.status_code == 200

    body = response.data
    assert body["restaurant"]["name"] == "Restaurante Teste"
    assert body["site"]["theme"] == {"primaryColor": "#E53935"}
    assert body["page"]["slug"] == "home"
    assert "Bem-vindo" in str(body["page"]["data"])
    assert {product["name"] for product in body["products"]} == {"Margherita", "Calabresa"}
    assert [category["name"] for category in body["categories"]] == ["Pizzas"]
    assert [promo["name"] for promo in body["promotions"]] == ["Calabresa"]
    assert "opening_hours" in body and "delivery" in body and "payment_methods" in body


def test_payload_publico_nao_expoe_custo_nem_codigo_interno(public_client, site, published_page, catalog):
    response = public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    product = response.data["products"][0]
    for hidden in ("estimated_cost", "margin_percent", "internal_code", "ean", "fiscal_profile"):
        assert hidden not in product


def test_endpoint_publico_nao_serve_rascunho(public_client, site, page, catalog):
    """Página nunca publicada não aparece — nem o conteúdo, nem na navegação."""
    response = public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    assert response.status_code == 200
    assert response.data["page"] is None
    assert response.data["pages"] == []


def test_site_inativo_devolve_404(public_client, site, published_page):
    site.is_active = False
    site.save(update_fields=["is_active", "updated_at"])
    assert public_client.get(f"/api/v1/public/storefront/{site.slug}/").status_code == 404


def test_slug_inexistente_devolve_404(public_client):
    assert public_client.get("/api/v1/public/storefront/nao-existe/").status_code == 404


def test_endpoint_publico_dispensa_autenticacao(public_client, site, published_page):
    assert "HTTP_AUTHORIZATION" not in public_client._credentials
    assert public_client.get(f"/api/v1/public/storefront/{site.slug}/").status_code == 200


def test_pagina_interna_por_slug(public_client, site, page, catalog):
    from apps.storefront.services.publishing import publish_page

    publish_page(page)
    contato = MenuPage.all_objects.create(
        account=site.account,
        restaurant=site.restaurant,
        site=site,
        title="Contato",
        slug="contato",
        draft_data=SIMPLE_PROJECT,
    )
    publish_page(contato)

    response = public_client.get(f"/api/v1/public/storefront/{site.slug}/?page=contato")
    assert response.data["page"]["slug"] == "contato"
    assert {row["slug"] for row in response.data["pages"]} == {"home", "contato"}


# ── Cache e invalidação ──────────────────────────────────────────────────────


def test_resposta_publica_e_cacheada(public_client, site, published_page, catalog):
    cache.clear()
    public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    assert storefront_cache.get_payload(site.restaurant_id, "home") is not None


def test_mudanca_de_preco_invalida_o_cache(
    public_client, site, published_page, catalog, django_capture_on_commit_callbacks
):
    """O sintoma que isto evita: o site vendendo pelo preço antigo.

    A invalidação é agendada para DEPOIS do commit (ver `schedule_invalidation`),
    por isso o teste captura e executa os callbacks: fora de teste, o commit da
    própria requisição faz isso sozinho.
    """
    public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    assert storefront_cache.get_payload(site.restaurant_id, "home") is not None

    product = catalog["products"][0]
    with django_capture_on_commit_callbacks(execute=True):
        product.sale_price = "59.90"
        product.save(update_fields=["sale_price", "updated_at"])

    assert storefront_cache.get_payload(site.restaurant_id, "home") is None
    response = public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    prices = {row["name"]: row["current_price"] for row in response.data["products"]}
    assert prices["Margherita"] == "59.90"


def test_publicar_invalida_o_cache(public_client, site, page, catalog, django_capture_on_commit_callbacks):
    from apps.storefront.services.publishing import publish_page

    publish_page(page)
    public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    assert storefront_cache.get_payload(site.restaurant_id, "home") is not None

    page.refresh_from_db()
    page.draft_data = {
        "pages": [{"frames": [{"component": {"type": "sf-heading", "tagName": "h1", "content": "Novidade"}}]}]
    }
    with django_capture_on_commit_callbacks(execute=True):
        page.save(update_fields=["draft_data", "updated_at"])
        publish_page(page)

    response = public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    assert "Novidade" in str(response.data["page"]["data"])


def test_invalidacao_e_por_restaurante(site, published_page, other_account_setup):
    """Mexer no cardápio de um restaurante não pode derrubar o cache do outro."""
    other_restaurant_id = other_account_setup["restaurant"].id
    storefront_cache.set_payload(site.restaurant_id, "home", {"marker": "a"})
    storefront_cache.set_payload(other_restaurant_id, "home", {"marker": "b"})

    storefront_cache.invalidate_storefront(site.restaurant_id, reason="teste")

    assert storefront_cache.get_payload(site.restaurant_id, "home") is None
    assert storefront_cache.get_payload(other_restaurant_id, "home") == {"marker": "b"}


# ── Domínios ─────────────────────────────────────────────────────────────────


def test_normalizacao_de_hostname():
    assert domain_service.normalize_hostname("HTTPS://Pizzaria.COM.br:8080/menu") == "pizzaria.com.br"
    assert domain_service.normalize_hostname("cardapio.exemplo.com.") == "cardapio.exemplo.com"


def test_dominio_verificado_resolve_o_site(site):
    MenuDomain.all_objects.create(
        account=site.account,
        restaurant=site.restaurant,
        site=site,
        hostname="cardapio.exemplo.com.br",
        domain_type=MenuDomain.TYPE_CUSTOM,
        verified=True,
        is_primary=True,
    )
    cache.clear()
    assert domain_service.resolve_site_by_hostname("cardapio.exemplo.com.br").id == site.id
    # Com `www.` também: é o mesmo site para quem digita o endereço.
    assert domain_service.resolve_site_by_hostname("www.cardapio.exemplo.com.br").id == site.id


def test_dominio_nao_verificado_nao_resolve(site):
    """Apontar um CNAME não pode bastar para servir o cardápio de alguém."""
    MenuDomain.all_objects.create(
        account=site.account,
        restaurant=site.restaurant,
        site=site,
        hostname="invasor.exemplo.com",
        domain_type=MenuDomain.TYPE_CUSTOM,
        verified=False,
    )
    cache.clear()
    assert domain_service.resolve_site_by_hostname("invasor.exemplo.com") is None


def test_subdominio_da_plataforma_resolve_pelo_slug(settings, site):
    settings.STOREFRONT_BASE_DOMAIN = "starchef.app"
    cache.clear()
    assert domain_service.resolve_site_by_hostname(f"{site.slug}.starchef.app").id == site.id


def test_endpoint_publico_por_host(public_client, site, published_page):
    MenuDomain.all_objects.create(
        account=site.account,
        restaurant=site.restaurant,
        site=site,
        hostname="cardapio.exemplo.com.br",
        domain_type=MenuDomain.TYPE_CUSTOM,
        verified=True,
    )
    cache.clear()
    response = public_client.get("/api/v1/public/storefront/by-host/?hostname=cardapio.exemplo.com.br")
    assert response.status_code == 200
    assert response.data["site"]["slug"] == site.slug


def test_host_desconhecido_devolve_404(public_client):
    cache.clear()
    assert public_client.get("/api/v1/public/storefront/by-host/?hostname=qualquer.com").status_code == 404


def test_admin_cadastra_dominio_e_recebe_token_de_verificacao(admin_client, ecommerce_account, site):
    response = admin_client.post(
        "/api/v1/storefront/domains/",
        {"site": str(site.id), "hostname": "Cardapio.Exemplo.com.BR", "domain_type": "custom"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["hostname"] == "cardapio.exemplo.com.br"
    assert response.data["verified"] is False
    assert response.data["verification_token"].startswith("starchef-verify-")


def test_dominio_duplicado_e_recusado(admin_client, ecommerce_account, site, other_account_setup):
    MenuDomain.all_objects.create(
        account=other_account_setup["account"],
        restaurant=other_account_setup["restaurant"],
        site=other_account_setup["site"],
        hostname="disputado.com.br",
        domain_type=MenuDomain.TYPE_CUSTOM,
    )
    response = admin_client.post(
        "/api/v1/storefront/domains/",
        {"site": str(site.id), "hostname": "disputado.com.br", "domain_type": "custom"},
        format="json",
    )
    assert response.status_code == 400


def test_dominio_reservado_da_plataforma_e_recusado(settings, admin_client, ecommerce_account, site):
    settings.STOREFRONT_RESERVED_HOSTNAMES = "app.starchef.com.br"
    response = admin_client.post(
        "/api/v1/storefront/domains/",
        {"site": str(site.id), "hostname": "app.starchef.com.br", "domain_type": "custom"},
        format="json",
    )
    assert response.status_code == 400


# ── Menus no payload público ────────────────────────────────────────────────


def test_payload_publico_traz_os_menus_resolvidos(public_client, site, published_page, catalog):
    """Os blocos leem daqui o que mostrar no banner, na nav e nas vitrines."""
    from apps.menu.services.default_menus import ensure_default_menus

    ensure_default_menus(site.restaurant)

    response = public_client.get(f"/api/v1/public/storefront/{site.slug}/")
    menus = response.data["menus"]

    assert {"categorias", "destaques", "ofertas", "navegacao-principal"} <= set(menus)
    # O menu dinâmico chega já resolvido: o site não refaz a consulta.
    assert [item["title"] for item in menus["categorias"]["items"]] == ["Pizzas"]
    assert [item["title"] for item in menus["ofertas"]["items"]] == ["Calabresa"]


def test_menu_inativo_nao_vai_para_o_site(public_client, site, published_page, catalog):
    from apps.menu.models import Menu
    from apps.menu.services.default_menus import ensure_default_menus

    ensure_default_menus(site.restaurant)
    Menu.all_objects.filter(account=site.account, slug="ofertas").update(is_active=False)

    response = public_client.get(f"/api/v1/public/storefront/{site.slug}/")

    assert "ofertas" not in response.data["menus"]
