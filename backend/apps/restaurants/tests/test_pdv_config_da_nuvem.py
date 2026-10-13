"""O PDV pega na nuvem, ao logar, o IP do server local do restaurante.

O endereço do servidor da loja era digitado em CADA terminal e em CADA
celular, e mudar o IP do servidor era refazer isso aparelho por aparelho.
Agora ele mora no cadastro do restaurante (`ip_server_local`): o app entra na
nuvem, pergunta `GET /pdv/config/` e passa a usar a loja.
"""
import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

URL = "/api/v1/pdv/config/"


def _com_ip(restaurant, valor):
    restaurant.ip_server_local = valor
    restaurant.save(update_fields=["ip_server_local"])


def test_devolve_o_ip_do_server_local_do_restaurante_do_usuario(api_client, restaurant):
    _com_ip(restaurant, "http://192.168.0.10")

    resposta = api_client.get(URL)

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["restaurant"] == str(restaurant.pk)
    # Pronto para usar: com o caminho da API, como o app espera.
    assert resposta.json()["ip_server_local"] == "http://192.168.0.10/api/v1"


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("192.168.0.10", "http://192.168.0.10/api/v1"),
        ("192.168.0.10:8000", "http://192.168.0.10:8000/api/v1"),
        ("http://loja.local:8000/api/v1/", "http://loja.local:8000/api/v1"),
        ("  ", ""),
    ],
)
def test_o_ip_digitado_de_qualquer_jeito_vira_o_endereco_da_api(
    api_client, restaurant, digitado, esperado
):
    _com_ip(restaurant, digitado)

    assert api_client.get(URL).json()["ip_server_local"] == esperado


def test_restaurante_sem_server_local_devolve_vazio(api_client, restaurant):
    assert api_client.get(URL).json()["ip_server_local"] == ""


def test_sem_login_nao_ha_config(restaurant):
    assert APIClient().get(URL).status_code == 401


def test_o_painel_edita_o_ip_no_cadastro_do_restaurante(api_client, restaurant):
    resposta = api_client.patch(f"/api/v1/restaurants/{restaurant.pk}/",
                                {"ip_server_local": "192.168.0.25"}, format="json")

    assert resposta.status_code == 200, resposta.content
    assert api_client.get(URL).json()["ip_server_local"] == "http://192.168.0.25/api/v1"


# O IP SERVER NUVEM vem do `API_URL` do .env da nuvem: sem IP local, o app manda
# tudo direto para ela. Mudar o domínio da nuvem não exige gerar o app de novo.
@pytest.mark.parametrize(
    ("api_url", "esperado"),
    [
        ("https://api.starchef.com.br/api/v1", "https://api.starchef.com.br/api/v1"),
        ("https://api.starchef.com.br", "https://api.starchef.com.br/api/v1"),
        # Relativa é o modo "mesma origem" do painel: não serve a um app.
        ("/api/v1", ""),
        ("", ""),
    ],
)
def test_devolve_o_ip_server_nuvem_do_api_url(api_client, restaurant, settings, api_url, esperado):
    settings.API_URL = api_url

    assert api_client.get(URL).json()["ip_server_nuvem"] == esperado


def test_somente_nuvem_ignora_o_ip_local_e_o_app_fica_na_nuvem(api_client, restaurant):
    """Com o servidor da loja fora de uso, o IP gravado forçava o app para ele:
    não havia como usar só a nuvem sem apagar o IP do cadastro."""
    _com_ip(restaurant, "192.168.0.10")
    restaurant.somente_nuvem = True
    restaurant.save(update_fields=["somente_nuvem"])

    corpo = api_client.get(URL).json()

    assert corpo["ip_server_local"] == ""
    assert corpo["somente_nuvem"] is True
