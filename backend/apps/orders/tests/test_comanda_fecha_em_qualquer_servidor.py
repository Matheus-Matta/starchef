"""Loja e nuvem fecham conta de comanda — mesmo com a outra no ar.

A v3.0.86 recusava na nuvem (409 `cobrar_na_loja`) com a loja dando sinal de
vida, e a v3.0.87 ainda recusava quem vinha pela janela do veredito. Mas o
sinal de vida é do `sync_worker`, não prova que o PDV alcança a loja, e o
operador pode PREFERIR a nuvem com a loja de reserva: a comanda não fechava
em lugar nenhum. Nenhum servidor recusa; o que impede cobrar duas vezes é a
identidade do recebimento (`payments/recebimento_por_uuid.py`).
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.command_items import launch_item
from apps.orders.tests.conftest import criar_vazio
from apps.restaurants.models import Command
from apps.synchronization.constants import NodeType
from apps.synchronization.models import SyncNode

pytestmark = pytest.mark.django_db


@pytest.fixture
def nuvem_com_loja(settings, account, restaurant):
    import uuid

    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "cloud"
    par = uuid.uuid4()
    SyncNode.objects.create(pair_id=par, account=account, node_type=NodeType.CLOUD,
                            name="Nuvem", is_self=True, status="ACTIVE")
    loja = SyncNode.objects.create(pair_id=par, account=account, restaurant=restaurant,
                                   node_type=NodeType.LOCAL, name="Loja", status="ACTIVE")
    from apps.synchronization.services import nodes

    nodes.invalidate_cache()
    yield loja
    nodes.invalidate_cache()


def _cobrar(api_client, contexto_tenant, account, restaurant, branch, produto, manager_user,
            **cabecalhos):
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     number=903)
    launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    pedido = criar_vazio(api_client, restaurant=restaurant, tipo="command").json()
    return api_client.post(f"/api/v1/orders/{pedido['id']}/attach-commands/",
                           {"commands": [str(comanda.pk)]}, format="json", **cabecalhos)


@pytest.mark.parametrize("cabecalhos", [{}, {"HTTP_X_DESVIO_DA_LOJA": "janela"}])
def test_nuvem_fecha_comanda_com_a_loja_no_ar(
    nuvem_com_loja, api_client, contexto_tenant, account, restaurant, branch, produto,
    manager_user, cabecalhos
):
    SyncNode.objects.filter(pk=nuvem_com_loja.pk).update(last_seen_at=timezone.now())

    resposta = _cobrar(api_client, contexto_tenant, account, restaurant, branch, produto,
                       manager_user, **cabecalhos)

    assert resposta.status_code == 200, resposta.content


def test_nuvem_fecha_comanda_com_a_loja_fora(
    nuvem_com_loja, api_client, contexto_tenant, account, restaurant, branch, produto, manager_user
):
    SyncNode.objects.filter(pk=nuvem_com_loja.pk).update(
        last_seen_at=timezone.now() - timedelta(minutes=5)
    )

    resposta = _cobrar(api_client, contexto_tenant, account, restaurant, branch, produto,
                       manager_user)

    assert resposta.status_code == 200, resposta.content
