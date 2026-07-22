"""
Testes de Ingredientes e Receitas (Sprint 3 · STC-031/033/034/035).

Cobre: estoque mínimo opcional e não-negativo, duplicidade de ingrediente,
CRUD de receita com itens, quantidade > zero e custo estimado.
"""
import uuid

import pytest

from apps.menu.models import Ingredient, Product, ProductCategory, Recipe

pytestmark = pytest.mark.django_db


def make_ingredient(account, restaurant, branch, name="Farinha", **extra):
    return Ingredient.objects.create(account=account, restaurant=restaurant, branch=branch, name=name, **extra)


def make_product(account, restaurant, branch, name="Bolo"):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name=name, internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price="20.00",
    )


# ── STC-031: estoque mínimo opcional e não-negativo ──────────────────────
def test_create_ingredient_without_minimum_stock(api_client, restaurant, branch):
    payload = {"name": "Sal", "unit": "kg", "restaurant": str(restaurant.id), "branch": str(branch.id)}
    resp = api_client.post("/api/v1/menu/ingredients/", payload, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["minimum_stock"] is None


def test_shared_ingredient_without_restaurant(db, account):
    # Ingredientes são compartilhados: criáveis sem restaurante (nível de conta).
    from django.contrib.auth import get_user_model
    from apps.accounts.models import UserProfile
    from conftest import _authenticated_client

    user = get_user_model().objects.create_user(username="admin-ing", password="x", is_superuser=True, is_staff=True)
    UserProfile.objects.create(account=account, user=user, profile_type=UserProfile.PROFILE_ADMIN)
    client = _authenticated_client(user)

    resp = client.post("/api/v1/menu/ingredients/", {"name": "Farinha Comum", "unit": "kg"}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["restaurant"] is None


def test_ingredient_negative_minimum_stock_rejected(api_client, restaurant, branch):
    payload = {"name": "Açúcar", "unit": "kg", "minimum_stock": "-5", "restaurant": str(restaurant.id), "branch": str(branch.id)}
    resp = api_client.post("/api/v1/menu/ingredients/", payload, format="json")
    assert resp.status_code == 400
    assert "minimum_stock" in resp.data["error"]["message"]


# ── STC-033: duplicidade de ingrediente ──────────────────────────────────
def test_duplicate_ingredient_returns_clear_error(api_client, account, restaurant, branch):
    make_ingredient(account, restaurant, branch, name="Leite")
    payload = {"name": "Leite", "unit": "l", "restaurant": str(restaurant.id), "branch": str(branch.id)}
    resp = api_client.post("/api/v1/menu/ingredients/", payload, format="json")
    # Duplicidade é rejeitada com mensagem compreensível (não 500 silencioso).
    assert resp.status_code == 400, resp.data
    assert "name" in str(resp.data["error"]["message"]).lower()


# ── STC-034/035: CRUD de receita + itens + custo ─────────────────────────
def test_create_recipe_and_add_items_updates_cost(api_client, account, restaurant, branch):
    product = make_product(account, restaurant, branch)
    flour = make_ingredient(account, restaurant, branch, name="Trigo", average_cost="2.0000")

    recipe_resp = api_client.post(
        "/api/v1/menu/recipes/",
        {"product": str(product.id), "yield_quantity": "1", "restaurant": str(restaurant.id), "branch": str(branch.id)},
        format="json",
    )
    assert recipe_resp.status_code == 201, recipe_resp.data
    recipe_id = recipe_resp.data["id"]

    item_resp = api_client.post(
        "/api/v1/menu/recipe-items/",
        {"recipe": str(recipe_id), "ingredient": str(flour.id), "quantity": "3", "unit": "kg", "restaurant": str(restaurant.id), "branch": str(branch.id)},
        format="json",
    )
    assert item_resp.status_code == 201, item_resp.data

    # O custo total da receita deve refletir os itens após o recálculo.
    # all_objects: fora do ciclo de request não há contexto de conta (TenantManager).
    recipe = Recipe.all_objects.get(id=recipe_id)
    assert recipe.total_cost > 0


def test_recipe_item_quantity_must_be_positive(api_client, account, restaurant, branch):
    product = make_product(account, restaurant, branch, name="Pão")
    ingredient = make_ingredient(account, restaurant, branch, name="Fermento")
    recipe = Recipe.objects.create(account=account, restaurant=restaurant, branch=branch, product=product)

    resp = api_client.post(
        "/api/v1/menu/recipe-items/",
        {"recipe": str(recipe.id), "ingredient": str(ingredient.id), "quantity": "0", "unit": "g", "restaurant": str(restaurant.id), "branch": str(branch.id)},
        format="json",
    )
    assert resp.status_code == 400
    assert "quantity" in resp.data["error"]["message"]
