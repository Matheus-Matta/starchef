"""A anotação da comanda nasce com o UUID que o aparelho deu a ela.

Achado no par Docker (`loadtest/dia_a_dia`): o garçom lançou 1 X-Burger no
segundo em que a loja reiniciava. A loja GRAVOU e morreu antes de responder; o
aparelho, sem resposta, não tinha como saber que chegou, e mandou à nuvem — a
comanda 538 ficou com dois. Tirar da fila depois do envio não resolve: o
primeiro envio já tinha acontecido.

Com o UUID do aparelho, a loja grava `U`, a nuvem grava `U`, e a sincronização
junta as duas pelo id: um item só. No mesmo servidor, o reenvio devolve o que
já existe.
"""
import uuid

import pytest

from apps.orders.models_command_item import CommandItem
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def comanda(account, restaurant, branch):
    return Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=538)


def _lancar(api_client, comanda, produto, item_id):
    return api_client.post(f"/api/v1/commands/{comanda.pk}/items/",
                           {"product": str(produto.pk), "quantity": 1, "id": item_id}, format="json")


def test_lanca_com_o_uuid_do_aparelho_e_o_reenvio_nao_duplica(
    api_client, contexto_tenant, comanda, produto
):
    item_id = str(uuid.uuid4())

    primeiro = _lancar(api_client, comanda, produto, item_id)
    reenvio = _lancar(api_client, comanda, produto, item_id)

    assert primeiro.status_code == 201, primeiro.content
    assert primeiro.json()["id"] == item_id
    assert reenvio.status_code in (200, 201) and reenvio.json()["id"] == item_id
    assert CommandItem.all_objects.filter(command=comanda).count() == 1


def test_uuid_de_outra_comanda_e_conflito(api_client, contexto_tenant, comanda, produto,
                                          account, restaurant, branch):
    outra = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=539)
    item_id = str(uuid.uuid4())
    _lancar(api_client, comanda, produto, item_id)

    resposta = _lancar(api_client, outra, produto, item_id)

    assert resposta.status_code == 409, resposta.content
    assert CommandItem.all_objects.filter(pk=item_id, command=comanda).exists()


def test_uuid_invalido_e_400(api_client, contexto_tenant, comanda, produto):
    assert _lancar(api_client, comanda, produto, "nao-e-uuid").status_code == 400


def test_reenvio_da_anotacao_vai_ao_historico(api_client, contexto_tenant, comanda, produto):
    from apps.synchronization.models import SyncDiscard

    item_id = str(uuid.uuid4())
    _lancar(api_client, comanda, produto, item_id)
    _lancar(api_client, comanda, produto, item_id)

    descarte = SyncDiscard.objects.get(entity_id=item_id)
    assert (descarte.motivo, descarte.entity_type) == (SyncDiscard.MOTIVO_REENVIO, "command_item")
    assert descarte.dados["product"] == str(produto.pk)


def test_uuid_que_chegou_pela_sincronizacao_no_mesmo_instante_devolve_o_existente(
    api_client, contexto_tenant, comanda, produto, monkeypatch
):
    """Achado no par Docker: o garçom reenviou à loja a anotação que a nuvem já
    tinha gravado, e a sincronização trazia a mesma anotação no MESMO instante.
    As duas inserções disputaram o UUID; o banco deixou passar uma (certo), e o
    garçom recebeu "valor duplicado" de uma anotação que existe."""
    item_id = str(uuid.uuid4())
    _lancar(api_client, comanda, produto, item_id)
    # A consulta antes de inserir não viu a linha (ela chegou entre as duas).
    monkeypatch.setattr("apps.orders.command_item_launch._ja_lancada", lambda *_: None)

    resposta = _lancar(api_client, comanda, produto, item_id)

    assert resposta.status_code in (200, 201), resposta.content
    assert resposta.json()["id"] == item_id
    assert CommandItem.all_objects.filter(command=comanda).count() == 1
