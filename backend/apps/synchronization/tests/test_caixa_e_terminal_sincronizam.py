"""Caixa e terminal atravessam os dois nós sem virar conflito.

Dois defeitos, o mesmo formato do pedido aberto na nuvem:

* **Caixa.** A sessão e os movimentos nascem na loja e sobem, mas o gerente
  aprova a sangria, transfere e libera a sessão pelo painel da NUVEM. Com
  `local_to_cloud` essa edição nem gerava evento: o PDV ficava "aguardando
  aprovação" de algo já aprovado.
* **Terminal.** É `CLOUD` (revogar é decisão do painel), mas quem o vê
  conectar é a loja. Cada conexão subia e virava conflito na nuvem. E cada lado
  cadastrava o terminal com um `uuid4` próprio: o índice único (conta,
  instalação) recusava o do outro, e a sessão que apontava para ele não
  aplicava.
"""
import uuid

import pytest
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, NodeType, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import conflicts, crypto
from apps.synchronization.tests.test_comanda_zerada_na_nuvem import (
    _agora,
    _decidir,
    _Linha,
    _subiu,
)

pytestmark = pytest.mark.django_db

_sequencia = iter(range(2000, 10_000))


def _na_nuvem(entidade, linha, *, local, remoto):
    return conflicts.decide(
        entidade, local_version=local, remote_version=remoto,
        receiving_node_type=NodeType.CLOUD, local_exists=True, local_instance=linha,
    )


def _pendente_na_nuvem(conta, no_nuvem, no_loja, entidade, linha, versao):
    """A nuvem gravou a linha e o evento ainda não foi confirmado pela loja."""
    payload = {"fields": {}}
    SyncEvent.objects.create(
        account=conta, source_node=no_nuvem, target_node=no_loja,
        direction=Direction.OUTBOUND, sequence=next(_sequencia), entity_type=entidade,
        entity_id=str(linha.pk), operation=Operation.UPSERT, entity_version=versao,
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.PENDING,
    )


@pytest.mark.parametrize("entidade", ["cash_register", "cash_movement"])
def test_aprovacao_do_painel_da_nuvem_chega_a_loja(como_loja, conta, no_loja, no_nuvem, entidade):
    """A loja abriu e subiu; a nuvem confirmou; o gerente aprovou no painel."""
    linha = _Linha(uuid.uuid4())
    aberto = _agora() - 60_000_000
    _subiu(conta, no_loja, no_nuvem, entidade, linha, versao=aberto,
           status=EventStatus.ACKNOWLEDGED)

    assert _decidir(entidade, linha, local=aberto, remoto=_agora()) == conflicts.APLICAR


@pytest.mark.parametrize("entidade", ["cash_register", "cash_movement"])
def test_edicao_do_caixa_que_a_nuvem_nao_viu_continua_conflito(
    como_loja, conta, no_loja, no_nuvem, entidade
):
    """O PDV fechou o caixa e isso ainda não subiu: são duas edições do dinheiro."""
    linha = _Linha(uuid.uuid4())
    fechado = _agora() - 1000
    _subiu(conta, no_loja, no_nuvem, entidade, linha, versao=fechado,
           status=EventStatus.PENDING)

    assert _decidir(entidade, linha, local=fechado, remoto=_agora()) == conflicts.CONFLITO


def test_conexao_do_terminal_na_loja_e_aplicada_na_nuvem(conta, no_loja, no_nuvem):
    """O PDV conectou na loja (nome, `last_seen_at`): a nuvem aceita."""
    linha = _Linha(uuid.uuid4())

    assert _na_nuvem("pdv_terminal", linha, local=_agora() - 60_000_000,
                     remoto=_agora()) == conflicts.APLICAR


def test_revogacao_ainda_nao_entregue_nao_e_desfeita_pela_loja(conta, no_loja, no_nuvem):
    """O painel revogou o terminal e a loja ainda não recebeu: a conexão que
    ela manda agora (ainda "ativo") não pode desfazer a revogação."""
    linha = _Linha(uuid.uuid4())
    revogado = _agora() - 1000
    _pendente_na_nuvem(conta, no_nuvem, no_loja, "pdv_terminal", linha, revogado)

    assert _na_nuvem("pdv_terminal", linha, local=revogado,
                     remoto=_agora()) == conflicts.CONFLITO


def test_o_mesmo_terminal_tem_o_mesmo_id_nos_dois_nos(conta):
    """Loja e nuvem cadastram a mesma instalação sozinhas — com o mesmo id."""
    from apps.payments.models import PdvTerminal
    from apps.payments.terminal_identity import terminal_id
    from apps.payments.terminals import resolve_terminal

    instalacao = str(uuid.uuid4())
    terminal = resolve_terminal(account=conta, installation_id=instalacao, name="Balcão 01")
    cadastrado_na_loja = terminal.pk
    PdvTerminal.all_objects.filter(pk=cadastrado_na_loja).delete()

    na_nuvem = resolve_terminal(account=conta, installation_id=instalacao, name="Balcão 01")

    assert na_nuvem.pk == cadastrado_na_loja == terminal_id(conta, instalacao)


def test_a_aprovacao_gravada_na_nuvem_vira_evento_para_a_loja(como_nuvem, conta, no_loja):
    """O portão da outbox: antes a nuvem nem gerava o evento do caixa."""
    from django.contrib.auth import get_user_model

    from apps.core.tenant import tenant_context
    from apps.payments.models import CashRegister, CashStation
    from apps.restaurants.models import Restaurant

    restaurante = Restaurant.objects.create(account=conta, legal_name="C LTDA", trade_name="C")
    operador = get_user_model().objects.create_user("caixa-painel", "p@t.test", "x")
    with tenant_context(conta):
        estacao = CashStation.objects.create(account=conta, restaurant=restaurante, name="Caixa 1")
        sessao = CashRegister.objects.create(
            account=conta, restaurant=restaurante, cash_station=estacao,
            status=CashRegister.STATUS_PENDING_APPROVAL, opened_by=operador,
        )
    SyncEvent.objects.all().delete()

    sessao.status = CashRegister.STATUS_OPEN
    sessao.approved_at = timezone.now()
    sessao.save()

    assert SyncEvent.objects.filter(
        direction=Direction.OUTBOUND, entity_type="cash_register",
        entity_id=str(sessao.pk), target_node=no_loja,
    ).exists()


def test_caixa_e_terminal_sobem_e_descem():
    from apps.synchronization.services.registry import registry

    for entidade in ["cash_register", "cash_movement", "pdv_terminal"]:
        assert registry.flows_to_local(entidade) and registry.flows_to_cloud(entidade)
