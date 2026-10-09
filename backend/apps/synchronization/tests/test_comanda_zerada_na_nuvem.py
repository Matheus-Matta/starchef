"""A comanda zerada no painel da NUVEM tem de chegar zerada à loja.

O defeito: o gerente zerava as comandas no painel web (nuvem), o painel
mostrava tudo livre — e o PDV, ligado ao servidor da loja, continuava com os
itens, mesmo saindo e voltando da tela. `command` e `command_item` são
`LOJA` ("a loja vence"), e a loja RECUSAVA toda versão mais nova vinda da
nuvem, abrindo um conflito por item. Só uma queda da loja abria exceção.

Hoje a regra é uma só, para toda entidade: a versão mais nova vence, e a mais
antiga não muda nada (`conflicts.py`). Inclusive quando a loja tem uma edição
ainda a caminho da nuvem — se ela é mais velha, perde; se é mais nova, a
versão da nuvem é que será ignorada quando chegar.
"""
import uuid

import pytest
from django.utils import timezone

import apps.synchronization.catalog  # noqa: F401 — registra o catálogo
from apps.synchronization.constants import Direction, EventStatus, NodeType, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import conflicts, crypto

pytestmark = pytest.mark.django_db


class _Linha:
    """Só o `pk` importa para a regra: é por ele que se procura o que subiu."""

    def __init__(self, pk):
        self.pk = pk


def _agora():
    return int(timezone.now().timestamp() * 1_000_000)


@pytest.fixture(autouse=True)
def _na_loja(como_loja):
    """Estas decisões são tomadas pela LOJA, recebendo da nuvem."""


_sequencia = iter(range(1, 10_000))


def _subiu(conta, no_loja, no_nuvem, entidade, linha, *, versao, status):
    payload = {"fields": {}}
    return SyncEvent.objects.create(
        account=conta, source_node=no_loja, target_node=no_nuvem,
        direction=Direction.OUTBOUND, sequence=next(_sequencia), entity_type=entidade,
        entity_id=str(linha.pk), operation=Operation.UPSERT, entity_version=versao,
        payload=payload, payload_checksum=crypto.checksum(payload), status=status,
    )


def _decidir(entidade, linha, *, local, remoto):
    return conflicts.decide(
        entidade, local_version=local, remote_version=remoto,
        receiving_node_type=NodeType.LOCAL, local_exists=True, local_instance=linha,
    )


@pytest.mark.parametrize("entidade", ["command", "command_item", "command_item_addon"])
def test_zerar_na_nuvem_e_aplicado_quando_a_loja_ja_entregou_tudo(
    conta, no_loja, no_nuvem, entidade
):
    """O defeito da loja: o item lançado no PDV subiu, a nuvem confirmou, o
    gerente zerou no painel — e a loja abria conflito em vez de aplicar."""
    linha = _Linha(uuid.uuid4())
    lancado = _agora() - 60_000_000
    _subiu(conta, no_loja, no_nuvem, entidade, linha, versao=lancado,
           status=EventStatus.ACKNOWLEDGED)

    assert _decidir(entidade, linha, local=lancado, remoto=_agora()) == conflicts.APLICAR


def test_linha_que_veio_da_nuvem_e_nunca_foi_mexida_na_loja_tambem_aplica(conta):
    """Sem nenhum envio da loja para esta linha, não há edição dela a proteger."""
    linha = _Linha(uuid.uuid4())

    assert _decidir(
        "command", linha, local=_agora() - 1000, remoto=_agora()
    ) == conflicts.APLICAR


@pytest.mark.parametrize(
    "status",
    [EventStatus.PENDING, EventStatus.PROCESSING, EventStatus.SENT,
     EventStatus.FAILED, EventStatus.DEAD],
)
def test_edicao_da_loja_a_caminho_perde_para_a_mais_nova_da_nuvem(
    conta, no_loja, no_nuvem, status
):
    """O garçom lançou na loja e isso ainda não chegou à nuvem; a nuvem manda
    uma versão MAIS NOVA. Antes virava conflito e a loja ficava com a velha."""
    linha = _Linha(uuid.uuid4())
    local = _agora() - 1000
    _subiu(conta, no_loja, no_nuvem, "command_item", linha, versao=local, status=status)

    assert _decidir("command_item", linha, local=local, remoto=_agora()) == conflicts.APLICAR


def test_versao_da_nuvem_mais_velha_que_a_edicao_da_loja_nao_muda_nada(conta, no_loja, no_nuvem):
    linha = _Linha(uuid.uuid4())
    agora = _agora()
    _subiu(conta, no_loja, no_nuvem, "command_item", linha, versao=agora,
           status=EventStatus.ACKNOWLEDGED)

    assert _decidir("command_item", linha, local=agora, remoto=agora - 1000) == conflicts.IGNORAR


@pytest.mark.parametrize("entidade", ["order", "order_item", "payment"])
def test_pedido_e_pagamento_seguem_a_mesma_regra(conta, entidade):
    """Com o terminal alternando entre os servidores, o mesmo pedido é editado
    nos dois: a edição mais nova é a que vale."""
    linha = _Linha(uuid.uuid4())

    assert _decidir(entidade, linha, local=_agora() - 1000, remoto=_agora()) == conflicts.APLICAR


def test_sem_a_linha_local_a_mais_nova_tambem_vence(conta):
    assert _decidir("command", None, local=_agora() - 1000, remoto=_agora()) == conflicts.APLICAR
