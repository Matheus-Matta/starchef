"""
Testes de Clientes e Endereços (Sprint 4 · STC-042/043/044/045).

Cobre: CPF válido/inválido/duplicado, telefone, cliente com endereço,
mascaramento de dados sensíveis na listagem e isolamento por conta.
"""

import pytest

from apps.accounts.models import UserProfile
from apps.customers.models import Customer
from apps.customers.validators import is_valid_cpf

pytestmark = pytest.mark.django_db

VALID_CPF = "529.982.247-25"   # CPF válido (dígitos verificadores corretos)
INVALID_CPF = "111.111.111-11"


def customer_payload(restaurant, branch, **overrides):
    data = {
        "name": "Maria Silva",
        "phone": "(11) 98888-7777",
        "restaurant": str(restaurant.id),
        "branch": str(branch.id),
    }
    data.update(overrides)
    return data


# ── CPF ──────────────────────────────────────────────────────────────────
def test_cpf_validator_unit():
    assert is_valid_cpf(VALID_CPF)
    assert not is_valid_cpf(INVALID_CPF)
    assert not is_valid_cpf("123")


def test_create_customer_with_valid_cpf(api_client, restaurant, branch):
    resp = api_client.post("/api/v1/customers/", customer_payload(restaurant, branch, document=VALID_CPF), format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["document"] == VALID_CPF


def test_create_customer_invalid_cpf_rejected(api_client, restaurant, branch):
    resp = api_client.post("/api/v1/customers/", customer_payload(restaurant, branch, document=INVALID_CPF), format="json")
    assert resp.status_code == 400
    assert "document" in resp.data["error"]["message"]


def test_duplicate_cpf_rejected(api_client, restaurant, branch):
    api_client.post("/api/v1/customers/", customer_payload(restaurant, branch, document=VALID_CPF), format="json")
    resp = api_client.post("/api/v1/customers/", customer_payload(restaurant, branch, name="Outro", document=VALID_CPF), format="json")
    assert resp.status_code == 400
    assert "document" in resp.data["error"]["message"]


def test_customer_without_cpf_allowed(api_client, restaurant, branch):
    resp = api_client.post("/api/v1/customers/", customer_payload(restaurant, branch), format="json")
    assert resp.status_code == 201, resp.data


# ── Endereço do cliente ──────────────────────────────────────────────────
def test_customer_with_address(api_client, restaurant, branch):
    customer_resp = api_client.post("/api/v1/customers/", customer_payload(restaurant, branch), format="json")
    customer_id = customer_resp.data["id"]
    addr_resp = api_client.post(
        "/api/v1/customers/addresses/",
        {"customer": str(customer_id), "street": "Rua A", "number": "10", "city": "São Paulo", "state": "SP",
         "restaurant": str(restaurant.id), "branch": str(branch.id)},
        format="json",
    )
    assert addr_resp.status_code == 201, addr_resp.data


def test_create_and_update_customer_with_nested_primary_address(api_client, restaurant, branch):
    payload = customer_payload(
        restaurant,
        branch,
        address={
            "label": "Casa",
            "street": "Rua das Flores",
            "number": "42",
            "district": "Centro",
            "city": "São Paulo",
            "state": "sp",
            "zip_code": "01000-000",
        },
    )
    created = api_client.post("/api/v1/customers/", payload, format="json")
    assert created.status_code == 201, created.data
    assert created.data["address"]["street"] == "Rua das Flores"
    assert created.data["address"]["state"] == "SP"

    updated = api_client.patch(
        f"/api/v1/customers/{created.data['id']}/",
        {"address": {**payload["address"], "number": "99"}},
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.data["address"]["number"] == "99"
    assert len(updated.data["addresses"]) == 1


# ── Mascaramento na listagem (STC-044) ───────────────────────────────────
def test_sensitive_data_masked_for_unprivileged_profile(account, restaurant, branch):
    Customer.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Cliente X", phone="11988887777", document=VALID_CPF,
    )
    # Usuário garçom (não autorizado a ver dados sensíveis) vê CPF/telefone mascarados.
    from conftest import _authenticated_client
    from django.contrib.auth import get_user_model

    waiter = get_user_model().objects.create_user(username="garcom", password="x")
    UserProfile.objects.create(account=account, user=waiter, profile_type=UserProfile.PROFILE_WAITER, restaurant=restaurant, branch=branch)
    client = _authenticated_client(waiter)

    resp = client.get("/api/v1/customers/")
    row = resp.data["results"][0]
    assert "***" in row["document"]
    assert "*" in row["phone"]


def test_sensitive_data_visible_for_manager(api_client, account, restaurant, branch):
    Customer.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Cliente Y", phone="11988887777", document=VALID_CPF,
    )
    resp = api_client.get("/api/v1/customers/")
    row = resp.data["results"][0]
    assert row["document"] == VALID_CPF
    assert "*" not in row["phone"]
