"""A comanda zerada no painel da NUVEM tem de chegar zerada à loja.

O defeito: o gerente zerava as comandas no painel web (nuvem), o painel
mostrava tudo livre — e o PDV, ligado ao servidor da loja, continuava com os
itens, mesmo saindo e voltando da tela. `command` e `command_item` são
`LOJA` ("a loja vence"), e a loja RECUSAVA toda versão mais nova vinda da
nuvem, abrindo um conflito por item. Só uma queda da loja abria exceção.

"A loja vence" existe para proteger uma edição da loja que a nuvem ainda não
viu. Se a loja já entregou tudo o que fez naquela linha, a edição da nuvem foi
feita EM CIMA da versão da loja: não há duas edições disputando, há uma só.
"""
import uuid

import pytest
from django.utils import timezone

import apps.synchronization.catalog  # noqa: F401 — registra o catálogo
from apps.synchronization.constants import Direction, EventStatus, NodeType, Operation
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import conflicts, crypto, nodes

pytestmark = pytest.mark.django_db


class _Linha:
    """Só o `pk` importa para a regra: é por ele que se procura o que subiu."""

    def __init__(self, pk):
        self.pk = pk


def _agora():
    return int(timezone.now().timestamp() * 1_000_000)


@pytest.fixture(autouse=True)
def _loja_sem_queda(como_loja, no_loja):
    """Loja conectada: a exceção da queda NÃO pode ser o que decide aqui."""
    SyncNode.objects.filter(pk=no_loja.pk).update(offline_since=None)
    nodes.invalidate_cache()


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
def test_edicao_da_loja_que_a_nuvem_ainda_nao_viu_continua_conflito(
    conta, no_loja, no_nuvem, status
):
    """A proteção que não pode cair junto: o garçom lançou na loja, isso ainda
    não chegou à nuvem, e a nuvem manda outra versão — são duas edições."""
    linha = _Linha(uuid.uuid4())
    local = _agora() - 1000
    _subiu(conta, no_loja, no_nuvem, "command_item", linha, versao=local, status=status)

    assert _decidir("command_item", linha, local=local, remoto=_agora()) == conflicts.CONFLITO


def test_versao_local_mais_nova_que_a_entregue_continua_conflito(conta, no_loja, no_nuvem):
    """A nuvem confirmou uma versão ANTERIOR; a loja mexeu de novo depois (e a
    gravação ainda nem virou evento). A edição nova da loja é protegida."""
    linha = _Linha(uuid.uuid4())
    entregue = _agora() - 60_000_000
    _subiu(conta, no_loja, no_nuvem, "command_item", linha, versao=entregue,
           status=EventStatus.ACKNOWLEDGED)

    assert _decidir(
        "command_item", linha, local=entregue + 5_000_000, remoto=_agora()
    ) == conflicts.CONFLITO


@pytest.mark.parametrize("entidade", ["order", "order_item", "payment"])
def test_pedido_e_pagamento_nao_entram_na_regra(conta, entidade):
    """Dinheiro segue como estava: divergência sem queda é decisão de gente."""
    linha = _Linha(uuid.uuid4())

    assert _decidir(entidade, linha, local=_agora() - 1000, remoto=_agora()) == conflicts.CONFLITO


def test_sem_a_linha_local_nada_muda(conta):
    """Quem chama sem a instância (como os testes antigos) decide como antes."""
    assert _decidir("command", None, local=_agora() - 1000, remoto=_agora()) == conflicts.CONFLITO
