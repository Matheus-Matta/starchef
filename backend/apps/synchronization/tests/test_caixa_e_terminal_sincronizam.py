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


@pytest.mark.parametrize("entidade", ["cash_register", "cash_movement"])
def test_aprovacao_do_painel_da_nuvem_chega_a_loja(como_loja, conta, no_loja, no_nuvem, entidade):
    """A loja abriu e subiu; a nuvem confirmou; o gerente aprovou no painel."""
    linha = _Linha(uuid.uuid4())
    aberto = _agora() - 60_000_000
    _subiu(conta, no_loja, no_nuvem, entidade, linha, versao=aberto,
           status=EventStatus.ACKNOWLEDGED)

    assert _decidir(entidade, linha, local=aberto, remoto=_agora()) == conflicts.APLICAR


@pytest.mark.parametrize("entidade", ["cash_register", "cash_movement"])
def test_no_caixa_tambem_vence_a_edicao_mais_nova(
    como_loja, conta, no_loja, no_nuvem, entidade
):
    """O PDV fechou o caixa e isso ainda não subiu; a nuvem mexeu DEPOIS: vence
    a da nuvem. A edição da loja, mais velha, será ignorada lá ao chegar."""
    linha = _Linha(uuid.uuid4())
    fechado = _agora() - 1000
    _subiu(conta, no_loja, no_nuvem, entidade, linha, versao=fechado,
           status=EventStatus.PENDING)

    assert _decidir(entidade, linha, local=fechado, remoto=_agora()) == conflicts.APLICAR


def test_conexao_do_terminal_na_loja_e_aplicada_na_nuvem(conta, no_loja, no_nuvem):
    """O PDV conectou na loja (nome, `last_seen_at`): a nuvem aceita."""
    linha = _Linha(uuid.uuid4())

    assert _na_nuvem("pdv_terminal", linha, local=_agora() - 60_000_000,
                     remoto=_agora()) == conflicts.APLICAR


def test_conexao_mais_nova_da_loja_nao_desfaz_a_revogacao_do_painel(
    como_nuvem, conta, no_loja, no_nuvem
):
    """O painel revogou às 10:00; a loja, sem saber, mandou às 10:01 a conexão
    do mesmo terminal ainda ativo. A conexão entra; a revogação fica."""
    from datetime import timedelta

    from apps.core.tenant import tenant_context
    from apps.payments.models import PdvTerminal
    from apps.restaurants.models import Restaurant
    from apps.synchronization.services import apply, serialization
    from apps.synchronization.services.registry import registry

    restaurante = Restaurant.objects.create(account=conta, legal_name="T LTDA", trade_name="T")
    with tenant_context(conta):
        terminal = PdvTerminal.objects.create(
            account=conta, restaurant=restaurante, installation_id="inst-1", name="Balcão",
            is_active=False, revoked_at=timezone.now(), revoked_reason="perdido",
        )

    visto = timezone.now() + timedelta(minutes=1)
    da_loja = PdvTerminal(
        id=terminal.id, account=conta, restaurant=restaurante, installation_id="inst-1",
        name="Balcão", is_active=True, revoked_at=None, last_seen_at=visto,
        created_at=terminal.created_at, updated_at=visto,
    )
    payload = serialization.build_payload(
        da_loja, registry.require("pdv_terminal"), origin_node_id=no_loja.id
    )
    evento = SyncEvent.objects.create(
        account=conta, source_node=no_loja, target_node=no_nuvem,
        direction=Direction.INBOUND, sequence=next(_sequencia), entity_type="pdv_terminal",
        entity_id=str(terminal.id), operation=Operation.UPSERT,
        entity_version=payload["entity_version"], payload=payload,
        payload_checksum=crypto.checksum(payload), status=EventStatus.RECEIVED,
    )
    apply.apply_event(evento)

    terminal = PdvTerminal.all_objects.get(pk=terminal.id)
    assert terminal.last_seen_at == visto
    assert terminal.is_active is False
    assert terminal.revoked_reason == "perdido"


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
