import pytest

from apps.menu.models import ProductCategory
from apps.payments.models import CashStation
from apps.restaurants.models import TableSector

pytestmark = pytest.mark.django_db


def test_relatorio_de_produtos_traz_as_opcoes_dos_filtros_na_mesma_resposta(
    api_client, account, restaurant, branch,
):
    categoria = ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Pizzas",
    )
    setor = TableSector.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Salão",
    )

    resposta = api_client.get("/api/v1/reports/products/")

    assert resposta.status_code == 200
    assert resposta.data["options"]["restaurants"] == [
        {"id": str(restaurant.id), "name": restaurant.trade_name},
    ]
    assert resposta.data["options"]["categories"] == [
        {"id": str(categoria.id), "name": categoria.name},
    ]
    assert resposta.data["options"]["sectors"] == [
        {"id": str(setor.id), "name": setor.name},
    ]


def test_relatorio_de_caixa_traz_os_caixas_na_mesma_resposta(
    api_client, account, restaurant,
):
    caixa = CashStation.objects.create(
        account=account, restaurant=restaurant, name="Caixa principal", code="CX01",
    )

    resposta = api_client.get("/api/v1/reports/cash-movements/")

    assert resposta.status_code == 200
    assert resposta.data["options"]["cash_stations"] == [
        {"id": str(caixa.id), "name": caixa.name, "code": caixa.code},
    ]
