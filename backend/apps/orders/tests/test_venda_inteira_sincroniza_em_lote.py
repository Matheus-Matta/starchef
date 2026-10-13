"""A venda na nuvem com loja matriculada: eventos em lote, e nenhum na simulação.

No alvo de carga, ligar a sincronização triplicava as consultas da venda
(10 itens: 214 -> 942), porque cada registro salvo gravava o seu evento na
hora. E a simulação, que é desfeita no fim, montava eventos só para jogá-los
fora — ao abrir a tela de pagamento.
"""
import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.orders.models import Order, OrderItem
from apps.orders.tests.test_venda_inteira import URL, _venda
from apps.synchronization.constants import NodeStatus, NodeType
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import crypto, nodes

pytestmark = pytest.mark.django_db


@pytest.fixture
def nuvem_com_loja(settings, restaurant):
    settings.SYNC_ENABLED = True
    settings.SYNC_ENVIRONMENT = "development"
    settings.SYNC_ENCRYPTION_KEY = crypto.generate_key()
    settings.SYNC_NODE_TYPE = "cloud"
    par = uuid.uuid4()
    nuvem = SyncNode.objects.create(pair_id=par, account=restaurant.account, node_type=NodeType.CLOUD,
                                    environment="development", name="Nuvem", status=NodeStatus.ACTIVE,
                                    is_self=True)
    SyncNode.objects.create(pair_id=par, account=restaurant.account, node_type=NodeType.LOCAL,
                            environment="development", name="Loja", status=NodeStatus.ACTIVE,
                            peer=nuvem)
    settings.SYNC_NODE_ID = str(nuvem.id)
    nodes.invalidate_cache()
    yield
    nodes.invalidate_cache()


def test_simulacao_nao_monta_evento_de_sincronizacao(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro, nuvem_com_loja
):
    corpo = dict(_venda(restaurant, produto, dinheiro, itens=3), simular=True, payments=[])

    with CaptureQueriesContext(connection) as ctx:
        assert api_client.post(URL, corpo, format="json").status_code == 200
    eventos = [q for q in ctx.captured_queries if "synchronization_syncevent" in q["sql"]]
    assert eventos == []  # nem montado: a simulação é desfeita de qualquer jeito
    assert SyncEvent.objects.count() == 0


def test_conclusao_grava_um_evento_por_registro(
    api_client, contexto_tenant, sem_caixa_obrigatorio, restaurant, produto, dinheiro, nuvem_com_loja
):
    corpo = _venda(restaurant, produto, dinheiro, itens=3, valor="75.00")

    with CaptureQueriesContext(connection) as ctx:
        assert api_client.post(URL, corpo, format="json").status_code == 201

    eventos = list(SyncEvent.objects.values_list("entity_type", "entity_id"))
    assert len(eventos) == len(set(eventos))  # o pedido salvo N vezes = 1 evento
    tipos = {tipo for tipo, _ in eventos}
    assert {"order", "order_item", "payment"} <= tipos
    pedido = Order.all_objects.get(pk=corpo["id"])
    assert ("order", str(pedido.pk)) in eventos
    itens = {str(pk) for pk in OrderItem.all_objects.filter(order=pedido).values_list("pk", flat=True)}
    assert itens <= {entidade for tipo, entidade in eventos if tipo == "order_item"}
    # Sem o lote eram ~5 consultas por registro capturado.
    assert len(ctx.captured_queries) < 160, len(ctx.captured_queries)
