"""Com a loja no ar, a nuvem não fecha conta de comanda.

Dois caixas — um na loja, outro grudado na nuvem — cobraram o MESMO cartão
com um minuto de diferença, antes de a sincronização contar à nuvem a primeira
cobrança (simulação do dia a dia, `loadtest/dia_a_dia`). A nuvem só cobra
comanda com a loja sem sinal de vida (`synchronization/services/loja_no_ar.py`).
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


def test_loja_no_ar_a_nuvem_recusa_e_manda_cobrar_na_loja(
    nuvem_com_loja, api_client, contexto_tenant, account, restaurant, branch, produto, manager_user
):
    SyncNode.objects.filter(pk=nuvem_com_loja.pk).update(last_seen_at=timezone.now())

    resposta = _cobrar(api_client, contexto_tenant, account, restaurant, branch, produto,
                       manager_user, HTTP_X_DESVIO_DA_LOJA="janela")

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == "cobrar_na_loja"


def test_loja_fora_a_nuvem_cobra(
    nuvem_com_loja, api_client, contexto_tenant, account, restaurant, branch, produto, manager_user
):
    SyncNode.objects.filter(pk=nuvem_com_loja.pk).update(
        last_seen_at=timezone.now() - timedelta(minutes=5)
    )

    resposta = _cobrar(api_client, contexto_tenant, account, restaurant, branch, produto,
                       manager_user)

    assert resposta.status_code == 200, resposta.content


def test_terminal_na_nuvem_cobra_mesmo_com_a_loja_no_ar(
    nuvem_com_loja, api_client, contexto_tenant, account, restaurant, branch, produto, manager_user
):
    """O impasse da v3.0.86: comanda que não fechava em lugar nenhum.

    O sinal de vida é do `sync_worker` da loja, não prova que o terminal a
    alcança. PDV configurado direto na nuvem (ou sem rota até a loja) era
    mandado de volta para uma loja que ele não usa: "não consigo finalizar
    pedido com comanda". Só quem vem pela janela do veredito é recusado.
    """
    SyncNode.objects.filter(pk=nuvem_com_loja.pk).update(last_seen_at=timezone.now())

    resposta = _cobrar(api_client, contexto_tenant, account, restaurant, branch, produto,
                       manager_user)

    assert resposta.status_code == 200, resposta.content
