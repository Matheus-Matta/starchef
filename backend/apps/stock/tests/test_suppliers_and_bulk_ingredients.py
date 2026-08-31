import pytest

from apps.menu.models import Ingredient
from apps.stock.models import StockEntry, StockEntryItem, StockLocation, Supplier

pytestmark = pytest.mark.django_db


@pytest.fixture
def account_with_logistica(account):
    account.enabled_modules = ["logistica"]
    account.save(update_fields=["enabled_modules"])
    return account


def make_supplier(account, user, name="Fornecedor Central"):
    return Supplier.all_objects.create(
        account=account,
        name=name,
        created_by=user,
        updated_by=user,
    )


def test_supplier_crud_is_available_in_logistics(api_client, account_with_logistica):
    response = api_client.post(
        "/api/v1/stock/suppliers/",
        {
            "name": "Distribuidora Brasil",
            "legal_name": "Distribuidora Brasil Ltda",
            "tax_id": "11.222.333/0001-81",
            "phone": "11999990000",
            "email": "compras@example.com",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["name"] == "Distribuidora Brasil"
    assert response.data["restaurant"] is None


def test_bulk_ingredients_create_all_rows_with_default_supplier(
    api_client, account_with_logistica, manager_user
):
    supplier = make_supplier(account_with_logistica, manager_user)

    response = api_client.post(
        "/api/v1/menu/ingredients/bulk/",
        {
            "items": [
                {"name": "Farinha", "unit": "kg", "supplier": str(supplier.id), "minimum_stock": "5"},
                {"name": "Oleo", "unit": "l", "supplier": str(supplier.id), "minimum_stock": "2"},
            ]
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert [item["name"] for item in response.data] == ["Farinha", "Oleo"]
    assert all(item["supplier"] == supplier.id for item in response.data)
    assert all(item["supplier_name"] == supplier.name for item in response.data)
    assert Ingredient.all_objects.filter(account=account_with_logistica, name__in=["Farinha", "Oleo"]).count() == 2


def test_bulk_ingredients_is_atomic_when_name_repeats(api_client, account_with_logistica):
    response = api_client.post(
        "/api/v1/menu/ingredients/bulk/",
        {"items": [{"name": "Leite", "unit": "l"}, {"name": "leite", "unit": "ml"}]},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert not Ingredient.all_objects.filter(account=account_with_logistica, name__iexact="leite").exists()


def test_stock_entry_inherits_unit_and_supplier_from_ingredient(
    api_client, account_with_logistica, restaurant, branch, manager_user
):
    supplier = make_supplier(account_with_logistica, manager_user)
    ingredient = Ingredient.all_objects.create(
        account=account_with_logistica,
        restaurant=restaurant,
        branch=branch,
        name="Acucar",
        unit="kg",
        supplier=supplier,
        created_by=manager_user,
        updated_by=manager_user,
    )
    location = StockLocation.all_objects.create(
        account=account_with_logistica,
        restaurant=restaurant,
        branch=branch,
        name="Deposito",
        created_by=manager_user,
        updated_by=manager_user,
    )

    response = api_client.post(
        "/api/v1/stock/entries/",
        {
            "location": str(location.id),
            "effective_date": "2026-08-31",
            "items": [
                {
                    "ingredient": str(ingredient.id),
                    "package_quantity": "2",
                    "content_per_package": "5",
                    "unit_cost": "12.50",
                }
            ],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["supplier"] == supplier.name
    assert response.data["items"][0]["content_unit"] == "kg"
    assert response.data["items"][0]["supplier"] == supplier.id
    assert response.data["items"][0]["supplier_name"] == supplier.name
    entry = StockEntry.all_objects.get(pk=response.data["id"])
    item = StockEntryItem.all_objects.get(entry=entry)
    assert item.supplier == supplier
    assert item.content_unit == ingredient.unit
