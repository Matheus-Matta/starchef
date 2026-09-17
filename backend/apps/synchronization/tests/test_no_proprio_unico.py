"""A instalação tem UMA identidade — e o lote sai pelo DESTINO.

Estes dois testes cobrem juntos um defeito que custou caro em produção: a
nuvem acumulava um nó `is_self` por loja matriculada, `self_node()` passava a
escolher um deles arbitrariamente, e o despacho — que filtrava por
`source_node` — devolvia lote vazio quando a escolha caía no nó "errado". O
resultado era uma loja conectada, autenticada, pedindo dados, e recebendo
`pending: 0` para sempre, com centenas de eventos parados em PENDING e nenhum
erro em lugar nenhum.
"""
import uuid

import pytest

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import dispatch, nodes, provisioning

pytestmark = pytest.mark.django_db


def test_matricular_varias_lojas_nao_cria_varios_nos_proprios(como_nuvem, conta):
    """Cada matrícula traz um `pair_id` novo; a identidade da nuvem não muda."""
    for numero in range(3):
        provisioning.provision_local_node(
            account=conta, name=f"Loja {numero}", cloud_endpoint="wss://dev-sync.local/ws/"
        )

    proprios = SyncNode.objects.filter(account=conta, node_type=NodeType.CLOUD, is_self=True)
    assert proprios.count() == 1
    assert proprios.first().pk == como_nuvem.pk


def test_ensure_self_node_ignora_o_pair_id_ao_reaproveitar(como_nuvem, conta):
    reaproveitado = provisioning.ensure_self_node(
        account=conta, node_type=NodeType.CLOUD, pair_id=uuid.uuid4()
    )
    assert reaproveitado.pk == como_nuvem.pk


def test_o_lote_sai_mesmo_com_dois_nos_proprios_no_banco(como_nuvem, conta, no_loja, settings):
    """A rede de segurança: filtrar por destino ignora a duplicata herdada.

    Bancos que já rodaram a versão com o defeito continuam com o nó extra. A
    correção do `ensure_self_node` impede novos, mas não apaga os antigos — e
    os eventos parados precisam sair assim mesmo.
    """
    Restaurant.objects.create(account=conta, legal_name="L1 LTDA", trade_name="L1")

    intruso = SyncNode.objects.create(
        pair_id=uuid.uuid4(), account=conta, node_type=NodeType.CLOUD,
        environment=como_nuvem.environment, name="Nuvem duplicada",
        status=como_nuvem.status, is_self=True,
    )
    # A instalação passa a resolver a identidade para o nó ERRADO: nenhum dos
    # eventos pendentes tem `source_node=intruso`.
    settings.SYNC_NODE_ID = str(intruso.id)
    nodes.invalidate_cache()
    assert nodes.self_node().pk == intruso.pk

    lote, _bytes = dispatch.collect_batch(nodes.self_node(), no_loja)
    assert lote, "o lote precisa sair pelo destino, não pela origem"
    assert all(e.target_node_id == no_loja.id for e in lote)
