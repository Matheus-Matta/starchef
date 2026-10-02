"""Faixa de números de comanda — é o que o PDV usa para imprimir etiquetas."""
import pytest

from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def comandas(account, restaurant, branch):
    for numero in (5, 10, 11, 50, 100, 101):
        Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=numero)


def _numeros(cliente, consulta):
    resposta = cliente.get(f"/api/v1/commands/?page_size=100&{consulta}")
    assert resposta.status_code == 200, resposta.content
    return [c["number"] for c in resposta.data["results"]]


def test_faixa_inclui_as_duas_pontas_e_vem_em_ordem(api_client, comandas):
    assert _numeros(api_client, "number_min=10&number_max=100") == [10, 11, 50, 100]


def test_so_um_dos_limites(api_client, comandas):
    assert _numeros(api_client, "number_min=100") == [100, 101]
    assert _numeros(api_client, "number_max=10") == [5, 10]


@pytest.mark.parametrize("consulta", ["number_min=abc", "number_max=1.5.2"])
def test_limite_que_nao_e_numero_e_400(api_client, comandas, consulta):
    assert api_client.get(f"/api/v1/commands/?{consulta}").status_code == 400
