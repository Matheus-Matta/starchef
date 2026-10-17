"""A retaguarda liga a pergunta "Imprimir a NFC-e?" do PDV pelo restaurante.

O PDV desktop e o web leem `ask_print_danfe` do cadastro do restaurante; sem
o campo na API, ligar a chave no painel não mudaria nada no caixa.
"""
import pytest

pytestmark = pytest.mark.django_db


def test_painel_liga_a_pergunta_do_danfe_e_a_api_devolve(admin_client, restaurant):
    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/", {"ask_print_danfe": True}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.data["ask_print_danfe"] is True
    restaurant.refresh_from_db()
    assert restaurant.ask_print_danfe is True
