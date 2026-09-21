"""O que a loja faz com o que a nuvem gravou enquanto ela estava fora.

O terminal desvia para a nuvem quando o servidor da loja cai — é o que mantém
o salão vendendo. Quando a loja volta, esses registros descem.

Linha NOVA nunca foi problema: não há o que conflitar. O problema é a linha que
já existe dos dois lados — a comanda que passou a estar ocupada, o pedido que
ganhou item. `conflict_policy=LOJA` dizia "a nuvem não manda nisto" e recusava
todas, uma a uma, sem aplicar nada. A loja seguia mostrando a comanda livre com
itens dentro, e ninguém via erro: o evento saía da fila marcado como aplicado.

A pergunta que desempata é estreita: *a loja mexeu nesta linha enquanto esteve
fora?* Se não mexeu, não existe edição da loja para proteger — que é a única
coisa que LOCAL_WINS existe para defender.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

import apps.synchronization.catalog  # noqa: F401 — registra o catálogo
from apps.synchronization.constants import NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import conflicts


pytestmark = pytest.mark.django_db


def _microssegundos(momento):
    return int(momento.timestamp() * 1_000_000)


@pytest.fixture
def queda(no_loja):
    """A loja ficou fora entre `inicio` e agora."""
    inicio = timezone.now() - timedelta(hours=2)
    SyncNode.objects.filter(pk=no_loja.pk).update(
        offline_since=inicio, last_seen_at=timezone.now()
    )
    from apps.synchronization.services import nodes

    nodes.invalidate_cache()
    return inicio


def _decidir(entity_type, *, local_version, remote_version):
    return conflicts.decide(
        entity_type,
        local_version=local_version,
        remote_version=remote_version,
        receiving_node_type=NodeType.LOCAL,
        local_exists=True,
        local_instance=None,
    )


def test_a_loja_APLICA_o_que_nao_tocou_durante_a_queda(como_loja, queda):
    """O defeito que esta regra existe para consertar."""
    antes_da_queda = _microssegundos(queda - timedelta(minutes=30))
    durante_a_queda = _microssegundos(queda + timedelta(minutes=30))

    assert _decidir(
        "command", local_version=antes_da_queda, remote_version=durante_a_queda
    ) == conflicts.APLICAR


def test_a_regra_vale_para_o_pedido_e_o_pagamento(como_loja, queda):
    """São as entidades que o terminal grava na nuvem durante a queda."""
    antes = _microssegundos(queda - timedelta(minutes=30))
    durante = _microssegundos(queda + timedelta(minutes=30))

    for entidade in ("order", "order_item", "command_item", "payment"):
        assert _decidir(
            entidade, local_version=antes, remote_version=durante
        ) == conflicts.APLICAR, f"{entidade} continuou virando conflito"


def test_linha_MEXIDA_depois_da_queda_continua_sendo_conflito(como_loja, queda):
    """A proteção que não pode cair junto.

    A loja voltou, alguém editou o pedido nela, e a nuvem manda outra versão:
    aí são duas edições de verdade, e a decisão é de uma pessoa.
    """
    depois = _microssegundos(timezone.now() - timedelta(minutes=1))
    remoto = _microssegundos(timezone.now())

    assert _decidir(
        "order", local_version=depois, remote_version=remoto
    ) == conflicts.CONFLITO


def test_sem_queda_registrada_nada_muda(como_loja, no_loja):
    """Nó que nunca caiu decide como sempre decidiu."""
    SyncNode.objects.filter(pk=no_loja.pk).update(offline_since=None)
    from apps.synchronization.services import nodes

    nodes.invalidate_cache()

    agora = _microssegundos(timezone.now())
    assert _decidir(
        "order", local_version=agora - 1000, remote_version=agora
    ) == conflicts.CONFLITO


def test_documento_fiscal_NAO_entra_na_excecao(como_loja, queda):
    """Nota fiscal nunca se resolve em silêncio, nem depois de uma queda.

    E não é só disciplina: o PDV nunca desvia o fiscal para a nuvem, então uma
    divergência aqui não veio de queda nenhuma — veio de outro lugar, e é
    exatamente o que precisa de gente olhando.
    """
    antes = _microssegundos(queda - timedelta(minutes=30))
    durante = _microssegundos(queda + timedelta(minutes=30))

    assert _decidir(
        "invoice", local_version=antes, remote_version=durante
    ) == conflicts.CONFLITO


def test_a_nuvem_nao_usa_a_excecao(como_nuvem, no_loja):
    """A janela é da LOJA. A nuvem não fica fora do ar esperando a loja."""
    SyncNode.objects.filter(pk=no_loja.pk).update(offline_since=timezone.now())

    agora = _microssegundos(timezone.now())

    assert conflicts._so_perdemos_a_atualizacao("order", NodeType.CLOUD, agora - 1000) is False

    # E na prática: a nuvem recebendo `order` da loja segue a política, que
    # aqui manda aplicar — não é a exceção que decide isso.
    assert conflicts.decide(
        "order",
        local_version=agora - 1000,
        remote_version=agora,
        receiving_node_type=NodeType.CLOUD,
        local_exists=True,
        local_instance=None,
    ) == conflicts.APLICAR
