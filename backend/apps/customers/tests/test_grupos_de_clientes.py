"""Grupos de clientes: um cliente participa de varios.

O vinculo e N:N de proposito. O cliente corporativo tambem faz aniversario, e
obriga-lo a escolher um grupo so transformaria o cadastro numa disputa entre
quem organiza a base.
"""
import json

import pytest

from apps.customers.models import Customer, CustomerGroup

pytestmark = pytest.mark.django_db

ROTA_GRUPOS = "/api/v1/customers/groups/"
ROTA_CLIENTES = "/api/v1/customers/"


def _grupo(admin_client, nome, **extra):
    resposta = admin_client.post(
        ROTA_GRUPOS,
        json.dumps({"name": nome, **extra}),
        content_type="application/json",
    )
    assert resposta.status_code == 201, resposta.content
    return resposta.json()


def test_cadastro_do_grupo_responde_no_padrao(admin_client):
    grupo = _grupo(admin_client, "VIP", description="Clientes recorrentes")

    assert grupo["name"] == "VIP"
    assert grupo["description"] == "Clientes recorrentes"
    # Grupo recem-criado nao tem ninguem, e a grade precisa dizer isso: um
    # grupo vazio e um com trezentos clientes tem o mesmo nome e a mesma cor.
    assert grupo["customer_count"] == 0


def test_o_nome_do_grupo_e_unico_na_conta(admin_client):
    """Dois "VIP" na mesma conta sao duas listas indistinguiveis depois."""
    _grupo(admin_client, "VIP")

    repetido = admin_client.post(
        ROTA_GRUPOS,
        json.dumps({"name": "VIP"}),
        content_type="application/json",
    )

    assert repetido.status_code == 409
    # A mensagem precisa falar de GRUPO, e nao "valor duplicado".
    assert "grupo" in str(repetido.json()["error"]["message"]).lower()


def test_cliente_participa_de_varios_grupos(admin_client, restaurant):
    vip = _grupo(admin_client, "VIP")
    aniversario = _grupo(admin_client, "Aniversariantes")

    resposta = admin_client.post(
        ROTA_CLIENTES,
        json.dumps({
            "name": "Maria",
            "phone": "11999990000",
            "restaurant": str(restaurant.id),
            "groups": [vip["id"], aniversario["id"]],
        }),
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert set(corpo["groups"]) == {vip["id"], aniversario["id"]}
    # O nome sai junto do id: sem isto a grade escreveria um uuid onde o
    # operador espera ler "VIP".
    assert sorted(corpo["group_names"]) == ["Aniversariantes", "VIP"]


def test_a_contagem_do_grupo_acompanha_os_vinculos(admin_client, restaurant):
    vip = _grupo(admin_client, "VIP")
    for nome in ("Ana", "Bruno"):
        admin_client.post(
            ROTA_CLIENTES,
            json.dumps({
                "name": nome, "phone": "11999990000",
                "restaurant": str(restaurant.id), "groups": [vip["id"]],
            }),
            content_type="application/json",
        )

    listagem = admin_client.get(ROTA_GRUPOS).json()
    encontrado = next(g for g in listagem["results"] if g["id"] == vip["id"])
    assert encontrado["customer_count"] == 2


def test_a_listagem_de_clientes_filtra_por_grupo(admin_client, restaurant):
    vip = _grupo(admin_client, "VIP")
    outro = _grupo(admin_client, "Corporativo")
    for nome, grupo in (("Ana", vip), ("Bruno", outro)):
        admin_client.post(
            ROTA_CLIENTES,
            json.dumps({
                "name": nome, "phone": "11999990000",
                "restaurant": str(restaurant.id), "groups": [grupo["id"]],
            }),
            content_type="application/json",
        )

    filtrado = admin_client.get(f"{ROTA_CLIENTES}?groups={vip['id']}").json()

    assert [c["name"] for c in filtrado["results"]] == ["Ana"]


def test_desvincular_nao_apaga_o_grupo(admin_client, restaurant, account):
    """Tirar o cliente do grupo e um gesto; apagar o grupo e outro."""
    vip = _grupo(admin_client, "VIP")
    criado = admin_client.post(
        ROTA_CLIENTES,
        json.dumps({
            "name": "Ana", "phone": "11999990000",
            "restaurant": str(restaurant.id), "groups": [vip["id"]],
        }),
        content_type="application/json",
    ).json()

    atualizado = admin_client.patch(
        f"{ROTA_CLIENTES}{criado['id']}/",
        json.dumps({"groups": []}),
        content_type="application/json",
    )

    assert atualizado.status_code == 200, atualizado.content
    assert atualizado.json()["groups"] == []
    assert CustomerGroup.all_objects.filter(pk=vip["id"]).exists()
    assert Customer.all_objects.filter(pk=criado["id"]).exists()
