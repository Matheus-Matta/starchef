"""
Testes da API do módulo Produtos (Sprint 2 · STC-023 / STC-027).

Cobre: produto com e sem categoria, ativo/inativo, categoria (criação válida,
duplicidade → 409, campo obrigatório), filtros/busca/ordenação/paginação e
isolamento por restaurante.
"""
import uuid

import pytest

from apps.accounts.models import Account, UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.menu.models import Product, ProductAddon, ProductCategory
from apps.restaurants.models import Branch, Restaurant

pytestmark = pytest.mark.django_db


# ── Helpers ──────────────────────────────────────────────────────────────
def make_category(account, restaurant, branch, name="Bebidas"):
    return ProductCategory.objects.create(account=account, restaurant=restaurant, branch=branch, name=name)


def product_payload(restaurant, branch, **overrides):
    data = {
        "name": "Coca-Cola",
        "internal_code": f"P{uuid.uuid4().hex[:6]}",
        "sale_price": "9.90",
        "restaurant": str(restaurant.id),
        "branch": str(branch.id),
    }
    data.update(overrides)
    return data


# ── Produtos: com e sem categoria (STC-022) ──────────────────────────────
def test_create_product_without_category(api_client, restaurant, branch):
    resp = api_client.post("/api/v1/menu/products/", product_payload(restaurant, branch), format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["category"] is None
    assert resp.data["category_name"] == "Sem categoria"


def test_product_can_be_shared_between_restaurants(admin_client, account, restaurant, branch):
    second = Restaurant.objects.create(
        account=account,
        legal_name="Restaurante Dois LTDA",
        trade_name="Restaurante Dois",
    )
    payload = product_payload(
        restaurant,
        branch,
        restaurants=[str(restaurant.id), str(second.id)],
    )

    created = admin_client.post("/api/v1/menu/products/", payload, format="json")

    assert created.status_code == 201, created.data
    assert set(map(str, created.data["restaurants"])) == {str(restaurant.id), str(second.id)}
    first_list = admin_client.get("/api/v1/menu/products/", {"restaurant": restaurant.id})
    second_list = admin_client.get("/api/v1/menu/products/", {"restaurant": second.id})
    assert created.data["id"] in {row["id"] for row in first_list.data["results"]}
    assert created.data["id"] in {row["id"] for row in second_list.data["results"]}


def test_create_product_with_category(api_client, account, restaurant, branch):
    category = make_category(account, restaurant, branch)
    payload = product_payload(restaurant, branch, category=str(category.id))
    resp = api_client.post("/api/v1/menu/products/", payload, format="json")
    assert resp.status_code == 201, resp.data
    assert str(resp.data["category"]) == str(category.id)
    assert resp.data["category_name"] == "Bebidas"


def test_create_product_without_branch_or_restaurant_inherits_from_profile(api_client):
    # branch/restaurant não são enviados: o servidor os herda do perfil.
    # Antes retornava "Este campo é obrigatório" (fantasma, sem campo no form).
    payload = {"name": "Herdado", "internal_code": f"P{uuid.uuid4().hex[:6]}", "sale_price": "5.00"}
    resp = api_client.post("/api/v1/menu/products/", payload, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["restaurant"] is not None


def test_create_with_null_restaurant_inherits_for_manager(api_client):
    # Front envia FK vazio como null; para gerente (tem restaurante no perfil),
    # o servidor herda em vez de falhar.
    payload = {"name": "Nulo", "internal_code": f"P{uuid.uuid4().hex[:6]}", "sale_price": "3.00", "restaurant": None, "branch": None}
    resp = api_client.post("/api/v1/menu/products/", payload, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["restaurant"] is not None


def test_variation_inherits_restaurant_from_product(api_client, restaurant, branch):
    # Criar variação sem enviar restaurant: herda do produto vinculado (não dá erro).
    product_resp = api_client.post("/api/v1/menu/products/", product_payload(restaurant, branch), format="json")
    product_id = product_resp.data["id"]
    resp = api_client.post(
        "/api/v1/menu/variations/",
        {"product": str(product_id), "name": "Grande", "price_delta": "2.00"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert str(resp.data["restaurant"]) == str(restaurant.id)


def test_link_and_unlink_addon_to_product(api_client, account, restaurant, branch):
    product_resp = api_client.post("/api/v1/menu/products/", product_payload(restaurant, branch), format="json")
    product_id = product_resp.data["id"]
    addon = ProductAddon.objects.create(account=account, restaurant=restaurant, branch=branch, name="Bacon", price="3.00")

    # Vincula o adicional ao produto.
    link = api_client.post(f"/api/v1/menu/products/{product_id}/link-addon/", {"addon": str(addon.id)}, format="json")
    assert link.status_code == 201, link.data
    detail = api_client.get(f"/api/v1/menu/products/{product_id}/")
    assert any(a["name"] == "Bacon" for a in detail.data["addons"])

    # Desvincula.
    unlink = api_client.post(f"/api/v1/menu/products/{product_id}/unlink-addon/", {"addon": str(addon.id)}, format="json")
    assert unlink.status_code == 204
    detail = api_client.get(f"/api/v1/menu/products/{product_id}/")
    assert detail.data["addons"] == []


def test_create_inactive_product(api_client, restaurant, branch):
    payload = product_payload(restaurant, branch, is_active=False)
    resp = api_client.post("/api/v1/menu/products/", payload, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["is_active"] is False


def test_product_missing_required_field_returns_field_error(api_client, restaurant, branch):
    payload = product_payload(restaurant, branch)
    payload.pop("sale_price")
    resp = api_client.post("/api/v1/menu/products/", payload, format="json")
    assert resp.status_code == 400
    # Envelope de erro: { error: { message: { campo: [...] } } }
    assert "sale_price" in resp.data["error"]["message"]


# ── Categorias: criação, duplicidade, obrigatório (STC-023) ───────────────
def test_create_category_valid(api_client, restaurant, branch):
    payload = {"name": "Sobremesas", "restaurant": str(restaurant.id), "branch": str(branch.id)}
    resp = api_client.post("/api/v1/menu/categories/", payload, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["name"] == "Sobremesas"


def test_create_category_duplicate_returns_field_error(api_client, account, restaurant, branch):
    make_category(account, restaurant, branch, name="Bebidas")
    payload = {"name": "Bebidas", "restaurant": str(restaurant.id), "branch": str(branch.id)}
    resp = api_client.post("/api/v1/menu/categories/", payload, format="json")
    # Conflito de nome vira erro claro no campo `name` (STC-023), não 500 silencioso.
    assert resp.status_code == 400, resp.data
    assert "name" in resp.data["error"]["message"]


def test_create_category_missing_name(api_client, restaurant, branch):
    payload = {"restaurant": str(restaurant.id), "branch": str(branch.id)}
    resp = api_client.post("/api/v1/menu/categories/", payload, format="json")
    assert resp.status_code == 400
    assert "name" in resp.data["error"]["message"]


def test_create_without_restaurant_scope_gives_clear_error(db, account):
    # Admin/superuser sem restaurante no perfil e sem enviar restaurant no payload,
    # num recurso que EXIGE restaurante (produto): erro claro no campo `restaurant`
    # (400), não 409 do banco.
    from django.contrib.auth import get_user_model
    from conftest import _authenticated_client

    user = get_user_model().objects.create_user(username="admin-sem-rest", password="x", is_superuser=True, is_staff=True)
    UserProfile.objects.create(account=account, user=user, role=ensure_system_roles(account)["admin"])  # sem restaurant
    client = _authenticated_client(user)

    resp = client.post("/api/v1/menu/products/", {"name": "Sem Escopo", "internal_code": "Z1", "sale_price": "1.00"}, format="json")
    assert resp.status_code == 400, resp.data
    assert "restaurant" in resp.data["error"]["message"]


def test_shared_category_can_be_created_without_restaurant(db, account):
    # Categorias são compartilhadas: admin sem escopo consegue criar (restaurant nulo).
    from django.contrib.auth import get_user_model
    from conftest import _authenticated_client

    user = get_user_model().objects.create_user(username="admin-shared", password="x", is_superuser=True, is_staff=True)
    UserProfile.objects.create(account=account, user=user, role=ensure_system_roles(account)["admin"])
    client = _authenticated_client(user)

    resp = client.post("/api/v1/menu/categories/", {"name": "Compartilhada"}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["restaurant"] is None


# ── Busca, ordenação, paginação ──────────────────────────────────────────
def test_products_search_and_ordering(api_client, restaurant, branch):
    for name, code in [("Água", "A1"), ("Suco", "S1"), ("Café", "C1")]:
        api_client.post("/api/v1/menu/products/", product_payload(restaurant, branch, name=name, internal_code=code), format="json")

    resp = api_client.get("/api/v1/menu/products/?search=Suco")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["name"] == "Suco"

    resp = api_client.get("/api/v1/menu/products/?ordering=name")
    names = [row["name"] for row in resp.data["results"]]
    assert names == sorted(names)


def test_products_pagination_envelope(api_client, restaurant, branch):
    resp = api_client.get("/api/v1/menu/products/?page_size=10")
    assert resp.status_code == 200
    for key in ("count", "next", "previous", "results"):
        assert key in resp.data


# ── Isolamento por restaurante (multi-tenant) ────────────────────────────
def test_products_isolated_by_account(api_client, account, restaurant, branch):
    api_client.post("/api/v1/menu/products/", product_payload(restaurant, branch, name="Meu Produto"), format="json")

    # Outra conta com seu próprio produto — não deve vazar para o cliente atual.
    other_account = Account.objects.create(name="Outra", slug=f"outra-{uuid.uuid4().hex[:8]}")
    other_restaurant = Restaurant.objects.create(
        account=other_account, legal_name="Outra LTDA", trade_name="Outra", cnpj=f"{uuid.uuid4().int % 10**14:014d}"
    )
    other_branch = Branch.objects.create(account=other_account, restaurant=other_restaurant, name="Matriz")
    Product.objects.create(
        account=other_account, restaurant=other_restaurant, branch=other_branch,
        name="Produto Alheio", internal_code="X1", sale_price="1.00",
    )

    resp = api_client.get("/api/v1/menu/products/")
    names = [row["name"] for row in resp.data["results"]]
    assert "Meu Produto" in names
    assert "Produto Alheio" not in names
