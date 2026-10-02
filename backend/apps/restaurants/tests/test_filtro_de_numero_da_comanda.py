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


def test_busca_pelo_numero_traz_a_exata_primeiro(api_client, comandas):
    """O PDV digita "10" e abre a primeira da lista: tem que ser a 10, não a 100.

    A busca é por "contém", então 10, 100 e 101 casam; a ordem por número é o
    que garante que a exata venha antes.
    """
    assert _numeros(api_client, "search=10&ordering=number") == [10, 100, 101]


def test_paginas_seguem_a_ordem_do_numero(api_client, comandas):
    """A rolagem do PDV pede página por página; nenhuma comanda some ou repete."""
    pagina1 = api_client.get("/api/v1/commands/?page_size=4&page=1&ordering=number").data
    pagina2 = api_client.get("/api/v1/commands/?page_size=4&page=2&ordering=number").data
    assert [c["number"] for c in pagina1["results"]] == [5, 10, 11, 50]
    assert [c["number"] for c in pagina2["results"]] == [100, 101]
    assert pagina1["count"] == 6 and pagina1["next"] and pagina2["next"] is None
