"""Provisionamento da configuracao fiscal e sua separacao do cadastro do restaurante.

Cobre a regressao que travava a edicao do restaurante: o cadastro e a tela fiscal
criavam cada um a sua `FiscalConfig` para a mesma filial, a segunda batia na
`unique_fiscal_config_by_branch` e o usuario recebia
"Ja existe um registro com estes dados (valor duplicado)" ao salvar.
"""
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.invoices.models import FiscalConfig
from apps.invoices.services import ensure_fiscal_config, restaurant_fiscal_branch

pytestmark = pytest.mark.django_db


@pytest.fixture
def financeiro(account):
    """Os endpoints `/fiscal/` exigem o modulo Financeiro habilitado na conta."""
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    return account


def field_errors(response):
    """Erros por campo dentro do envelope padrao da API."""
    return response.data.get("error", {}).get("message", response.data)


def test_ensure_fiscal_config_is_idempotent(restaurant):
    first = ensure_fiscal_config(restaurant)
    second = ensure_fiscal_config(restaurant)

    assert first.pk == second.pk
    assert FiscalConfig.all_objects.filter(restaurant=restaurant).count() == 1


def test_ensure_fiscal_config_revives_soft_deleted_config(restaurant):
    config = ensure_fiscal_config(restaurant)
    FiscalConfig.all_objects.filter(pk=config.pk).update(deleted_at=timezone.now())

    revived = ensure_fiscal_config(restaurant)

    assert revived.pk == config.pk
    assert revived.deleted_at is None
    assert FiscalConfig.all_objects.filter(restaurant=restaurant).count() == 1


def test_ensure_fiscal_config_only_fills_blank_emitter_fields(restaurant):
    config = ensure_fiscal_config(restaurant)
    FiscalConfig.all_objects.filter(pk=config.pk).update(corporate_name="Razao ajustada na tela fiscal", city="")
    restaurant.city = "Sao Paulo"
    restaurant.save()

    refreshed = ensure_fiscal_config(restaurant)

    # O que a tela fiscal definiu permanece; so o campo vazio e semeado.
    assert refreshed.corporate_name == "Razao ajustada na tela fiscal"
    assert refreshed.city == "Sao Paulo"


def test_ensure_fiscal_config_copies_restaurant_district_when_blank(restaurant):
    config = ensure_fiscal_config(restaurant)
    restaurant.district = "Centro"
    restaurant.save(update_fields=["district", "updated_at"])

    refreshed = ensure_fiscal_config(restaurant)

    assert refreshed.pk == config.pk
    assert refreshed.district == "Centro"


def test_restaurant_update_keeps_single_fiscal_config(admin_client, restaurant):
    ensure_fiscal_config(restaurant)

    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.pk}/",
        {"zip_code": "01001-000", "city": "Sao Paulo", "state": "SP"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert FiscalConfig.all_objects.filter(restaurant=restaurant).count() == 1


def test_restaurant_update_survives_soft_deleted_fiscal_config(admin_client, restaurant):
    config = ensure_fiscal_config(restaurant)
    FiscalConfig.all_objects.filter(pk=config.pk).update(deleted_at=timezone.now())

    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.pk}/", {"zip_code": "01001-000"}, format="json"
    )

    assert response.status_code == 200, response.data
    restaurant.refresh_from_db()
    assert restaurant.zip_code == "01001-000"


@patch("apps.invoices.focus.enqueue_focus_company_sync")
def test_restaurant_update_does_not_trigger_focus_sync(mock_enqueue, admin_client, restaurant):
    ensure_fiscal_config(restaurant, provider=FiscalConfig.PROVIDER_FOCUS_NFE)

    response = admin_client.patch(f"/api/v1/restaurants/{restaurant.pk}/", {"phone": "1133334444"}, format="json")

    assert response.status_code == 200, response.data
    # Salvar o cadastro nao pode mais disparar a Focus: com o emitente ainda
    # incompleto isso so produzia o erro "Empresa nao sincronizada: ... CEP".
    mock_enqueue.assert_not_called()


@patch("apps.invoices.focus.enqueue_focus_company_sync")
def test_explicit_provider_change_still_syncs(mock_enqueue, admin_client, restaurant):
    ensure_fiscal_config(restaurant)

    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.pk}/", {"fiscal_provider": "focus_nfe"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.data["fiscal_provider"] == FiscalConfig.PROVIDER_FOCUS_NFE
    mock_enqueue.assert_called_once()


def test_duplicate_cnpj_is_a_field_error_not_a_conflict(admin_client, restaurant):
    response = admin_client.post(
        "/api/v1/restaurants/",
        {"legal_name": "Outra Empresa LTDA", "trade_name": "Outra", "cnpj": restaurant.cnpj},
        format="json",
    )

    assert response.status_code == 400, response.data
    errors = field_errors(response)
    assert "cnpj" in errors
    assert restaurant.trade_name in str(errors["cnpj"])


def test_duplicate_cnpj_of_deleted_restaurant_explains_itself(admin_client, restaurant):
    restaurant.delete()  # soft delete: o unique do banco continua valendo

    response = admin_client.post(
        "/api/v1/restaurants/",
        {"legal_name": "Outra Empresa LTDA", "trade_name": "Outra", "cnpj": restaurant.cnpj},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "ja excluido" in str(field_errors(response)["cnpj"])


def test_for_restaurant_returns_the_same_config_every_time(admin_client, restaurant, financeiro):
    first = admin_client.get("/api/v1/fiscal/config/for-restaurant/", {"restaurant": str(restaurant.pk)})
    second = admin_client.get("/api/v1/fiscal/config/for-restaurant/", {"restaurant": str(restaurant.pk)})

    assert first.status_code == 200, first.data
    assert second.status_code == 200, second.data
    assert first.data["id"] == second.data["id"]
    assert first.data["restaurant_name"] == restaurant.trade_name
    assert FiscalConfig.all_objects.filter(restaurant=restaurant).count() == 1


def test_fiscal_config_accepts_emitter_district(admin_client, restaurant, financeiro):
    config = ensure_fiscal_config(restaurant)

    response = admin_client.patch(
        f"/api/v1/fiscal/config/{config.pk}/",
        {"district": "Centro"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["district"] == "Centro"
    config.refresh_from_db()
    assert config.district == "Centro"


def test_for_restaurant_lists_what_is_still_missing(admin_client, restaurant, financeiro):
    response = admin_client.get("/api/v1/fiscal/config/for-restaurant/", {"restaurant": str(restaurant.pk)})

    assert response.status_code == 200, response.data
    missing = {item["field"] for item in response.data["focus_missing_fields"]}
    # O restaurante da fixture nao tem endereco/cidade/UF/CEP.
    assert {
        "ie",
        "address_line",
        "address_number",
        "district",
        "city",
        "uf",
        "zip_code",
        "csc_id",
        "csc_token",
    } <= missing


def test_for_restaurant_requires_the_restaurant_param(admin_client, financeiro):
    response = admin_client.get("/api/v1/fiscal/config/for-restaurant/")

    assert response.status_code == 400, response.data


def test_for_restaurant_404s_for_an_unknown_or_malformed_id(admin_client, financeiro):
    unknown = admin_client.get(
        "/api/v1/fiscal/config/for-restaurant/", {"restaurant": "00000000-0000-0000-0000-000000000000"}
    )
    malformed = admin_client.get("/api/v1/fiscal/config/for-restaurant/", {"restaurant": "nao-e-um-uuid"})

    assert unknown.status_code == 404, unknown.data
    # Um id invalido na querystring e "nao encontrado", nunca um 500.
    assert malformed.status_code == 404, malformed.data


def test_second_fiscal_config_for_the_same_branch_is_rejected_with_a_message(admin_client, restaurant, financeiro):
    config = ensure_fiscal_config(restaurant)
    branch = restaurant_fiscal_branch(restaurant)

    response = admin_client.post(
        "/api/v1/fiscal/config/",
        {"restaurant": str(restaurant.pk), "branch": str(branch.pk), "provider": "manual"},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "branch" in field_errors(response)
    assert FiscalConfig.all_objects.filter(pk=config.pk).count() == 1
