"""Duas chamadas com a MESMA chave ao mesmo tempo gravam uma vez só.

A tentativa que o terminal repete com a mesma `Idempotency-Key` (resposta
perdida na rede) pode chegar enquanto a primeira ainda está no meio. As duas
passam pela conferência ("chave nova") e executam. Quando a segunda foi gravar
a chave e bateu na primeira, o middleware IGNORAVA o erro: a resposta saía
como sucesso, e a gravação dela — o segundo item, o segundo recebimento —
ficava ao lado da primeira. O certo é desfazer o que ela fez e devolver a
resposta que a primeira já gravou.
"""
import pytest

from apps.core.models import IdempotencyRecord
from apps.orders.models_command_item import CommandItem
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db

CHAVE = "terminal-1-op-42"


def test_a_segunda_desfaz_o_que_gravou_e_devolve_a_resposta_da_primeira(
    api_client, contexto_tenant, account, restaurant, branch, produto, monkeypatch
):
    from apps.core.idempotency import IdempotencyMiddleware

    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     number=902)
    # A primeira tentativa já gravou e confirmou a chave...
    IdempotencyRecord.objects.create(
        account=account, key=CHAVE, method="POST",
        path=f"/api/v1/commands/{comanda.pk}/items/", request_fingerprint="x",
        status_code=201, response_body={"id": "o-item-da-primeira"},
    )
    # ...mas esta passou pela conferência ANTES de ela confirmar.
    monkeypatch.setattr(IdempotencyMiddleware, "_gravada", staticmethod(lambda *_a: None))

    resposta = api_client.post(f"/api/v1/commands/{comanda.pk}/items/",
                               {"product": str(produto.pk), "quantity": 1}, format="json",
                               HTTP_IDEMPOTENCY_KEY=CHAVE)

    assert resposta.json().get("id") == "o-item-da-primeira"
    assert CommandItem._base_manager.filter(command=comanda).count() == 0
