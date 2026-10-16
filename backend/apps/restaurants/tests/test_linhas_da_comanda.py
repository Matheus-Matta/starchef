"""A lista de linhas da comanda da pesagem: gravada no restaurante e sincronizada."""
import uuid

import pytest

from apps.synchronization.catalog import registry
from apps.synchronization.services.serialization import serialize

pytestmark = pytest.mark.django_db


def test_o_restaurante_grava_produtos_e_linhas_em_branco(admin_client, restaurant):
    produto = str(uuid.uuid4())
    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/",
        {"linhas_da_comanda": [
            {"tipo": "produto", "produto": produto, "lixo": "x"},
            {"tipo": "branco"},
        ]},
        format="json",
    )

    assert response.status_code == 200, response.data
    restaurant.refresh_from_db()
    # Chave desconhecida não entra no banco: o formato é o do módulo, só.
    assert restaurant.linhas_da_comanda == [
        {"tipo": "produto", "produto": produto},
        {"tipo": "branco"},
    ]


@pytest.mark.parametrize(
    "linhas",
    [
        "texto",
        [{"tipo": "bebida"}],
        [{"tipo": "produto", "produto": "nao-e-uuid"}],
        [{"tipo": "branco"}] * 21,
    ],
)
def test_linha_que_nao_e_produto_nem_branco_e_recusada_com_400(admin_client, restaurant, linhas):
    """Entrada errada é 400 — o PDV mostra o motivo e não reenvia."""
    response = admin_client.patch(
        f"/api/v1/restaurants/{restaurant.id}/",
        {"linhas_da_comanda": linhas},
        format="json",
    )

    assert response.status_code == 400


def test_as_linhas_da_comanda_viajam_no_payload_da_sincronizacao(restaurant):
    """Campo novo não tem trava automática: a balança da loja precisa da lista da nuvem."""
    restaurant.linhas_da_comanda = [{"tipo": "branco"}]
    restaurant.save(update_fields=["linhas_da_comanda"])

    payload = serialize(restaurant, registry.require("restaurant"))

    assert payload["linhas_da_comanda"] == [{"tipo": "branco"}]
