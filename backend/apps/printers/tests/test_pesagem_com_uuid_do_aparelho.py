"""A pesagem lançada na comanda tem o UUID que o aparelho deu a ela.

Achado no par Docker (`loadtest/dia_a_dia`): a balança mandou o peso no segundo
em que a loja reiniciava; a loja gravou e caiu antes de responder, o terminal
mandou à nuvem — "pesagem 0,251 kg x2" na comanda. Com o UUID do aparelho, a
leitura, a anotação, os adicionais e a rodada de produção têm ids CALCULADOS
dele: o reenvio, no mesmo servidor ou no outro, é a MESMA pesagem.
"""
import uuid

import pytest

from apps.accounts.tests.test_perfil_balanca_ponta_a_ponta import estacao, operador  # noqa: F401
from apps.core.tenant import tenant_context
from apps.orders.models import CommandItem
from apps.printers.models import ScaleReading
from apps.printers.pesagem_por_uuid import id_da_anotacao

pytestmark = pytest.mark.django_db


def _pesar(operador, estacao, pesagem_id, peso="0.251"):  # noqa: F811
    return operador.post(f"/api/v1/scales/{estacao['balanca'].pk}/checkout-command/", {
        "command_code": estacao["comanda"].code, "weight_kg": peso, "id": pesagem_id,
        "print": False,
    }, format="json")


def test_reenvio_da_pesagem_e_a_mesma_pesagem(operador, estacao, account):  # noqa: F811
    pesagem_id = str(uuid.uuid4())

    primeira = _pesar(operador, estacao, pesagem_id)
    reenvio = _pesar(operador, estacao, pesagem_id)

    assert primeira.status_code == 201, primeira.data
    assert reenvio.status_code in (200, 201), reenvio.data
    with tenant_context(account):
        itens = CommandItem.all_objects.filter(command=estacao["comanda"])
        assert itens.count() == 1
        assert itens.get().pk == id_da_anotacao(pesagem_id)
        assert ScaleReading.all_objects.filter(pk=pesagem_id).count() == 1
    assert reenvio.data["weighed_item"]["id"] == str(id_da_anotacao(pesagem_id))
