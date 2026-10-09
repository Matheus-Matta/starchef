"""A regra única do clone: vence a versão mais nova; a mais antiga não muda nada.

A versão é o `updated_at` de ORIGEM em microssegundos. Dois defeitos faziam a
comparação mentir:

* o `save()` da aplicação trocava o `updated_at` vindo do outro lado por
  "agora". A edição que a nuvem fez às 10:00:03 e chegou depois de a loja
  aplicar a de 10:00:00 (às 10:00:05) parecia MAIS VELHA que a linha local e
  era descartada;
* a política `LOJA`/`NUVEM` recusava versão mais nova do outro lado e abria
  conflito — com o terminal alternando entre os dois servidores, toda edição
  de pedido virava conflito e a loja ficava com o total antigo.
"""
import copy
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, crypto, serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db

_sequencia = iter(range(1, 10_000))


def _versao(momento):
    return int(momento.timestamp() * 1_000_000)


def _payload(grupo, no_origem, *, quando, **mudancas):
    """O retrato que o OUTRO lado gravou em `quando`, sem tocar no banco daqui."""
    retrato = copy.copy(grupo)
    for campo, valor in mudancas.items():
        setattr(retrato, campo, valor)
    retrato.updated_at = quando
    return serialization.build_payload(
        retrato, registry.require("customer_group"), origin_node_id=no_origem.id
    )


def _entregar(conta, origem, destino, payload):
    evento = SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=next(_sequencia),
        entity_type=payload["entity_type"], entity_id=payload["entity_id"],
        operation=Operation.UPSERT, entity_version=payload["entity_version"],
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.RECEIVED,
    )
    apply.apply_event(evento)
    evento.refresh_from_db()
    return evento


@pytest.fixture
def grupo(conta):
    from apps.core.tenant import tenant_context
    from apps.customers.models import CustomerGroup
    from apps.restaurants.models import Restaurant

    restaurante = Restaurant.objects.create(account=conta, legal_name="G LTDA", trade_name="G")
    with tenant_context(conta):
        return CustomerGroup.objects.create(
            account=conta, restaurant=restaurante, name="Original"
        )


def _recarregar(grupo):
    return type(grupo)._base_manager.get(pk=grupo.pk)


def test_aplicar_guarda_o_horario_de_origem(como_loja, conta, no_nuvem, no_loja, grupo):
    quando = timezone.now() + timedelta(seconds=30)
    _entregar(conta, no_nuvem, no_loja, _payload(grupo, no_nuvem, quando=quando, name="Nuvem"))

    local = _recarregar(grupo)
    assert local.name == "Nuvem"
    assert _versao(local.updated_at) == _versao(quando)


def test_edicao_mais_nova_que_chega_depois_da_aplicacao_nao_e_descartada(
    como_loja, conta, no_nuvem, no_loja, grupo
):
    """O cenário: 10:00:00 aplicada às 10:00:05; a de 10:00:03 chega depois."""
    base = timezone.now() + timedelta(seconds=10)
    _entregar(conta, no_nuvem, no_loja, _payload(grupo, no_nuvem, quando=base, name="Primeira"))
    _entregar(conta, no_nuvem, no_loja,
              _payload(grupo, no_nuvem, quando=base + timedelta(seconds=3), name="Segunda"))

    assert _recarregar(grupo).name == "Segunda"


def test_versao_mais_antiga_nao_muda_nada(como_loja, conta, no_nuvem, no_loja, grupo):
    novo = timezone.now() + timedelta(minutes=5)
    _entregar(conta, no_nuvem, no_loja, _payload(grupo, no_nuvem, quando=novo, name="Nova"))
    evento = _entregar(conta, no_nuvem, no_loja,
                       _payload(grupo, no_nuvem, quando=novo - timedelta(minutes=1), name="Velha"))

    local = _recarregar(grupo)
    assert local.name == "Nova"
    assert _versao(local.updated_at) == _versao(novo)
    assert evento.status == EventStatus.APPLIED  # sai da fila, sem mexer no dado


def test_versao_mais_antiga_por_um_milissegundo_tambem_nao_muda(
    como_loja, conta, no_nuvem, no_loja, grupo
):
    novo = timezone.now() + timedelta(minutes=5)
    _entregar(conta, no_nuvem, no_loja, _payload(grupo, no_nuvem, quando=novo, name="Nova"))
    _entregar(conta, no_nuvem, no_loja,
              _payload(grupo, no_nuvem, quando=novo - timedelta(milliseconds=1), name="Velha"))

    assert _recarregar(grupo).name == "Nova"


@pytest.mark.parametrize("entidade", ["order", "command_item", "cash_register", "product", "invoice"])
@pytest.mark.parametrize("recebe", ["LOCAL", "CLOUD"])
def test_nos_dois_sentidos_a_mais_nova_aplica_e_a_mais_antiga_e_ignorada(
    como_loja, entidade, recebe
):
    """Sem conflito por política: a regra é a mesma para toda entidade."""
    from apps.synchronization.services import conflicts

    agora = _versao(timezone.now())

    def decidir(remota):
        return conflicts.decide(
            entidade, local_version=agora, remote_version=remota,
            receiving_node_type=recebe, local_exists=True, local_instance=None,
        )

    assert decidir(agora + 1_000) == conflicts.APLICAR
    assert decidir(agora - 1_000) == conflicts.IGNORAR


def test_todo_dado_de_negocio_viaja_nos_dois_sentidos():
    for entrada in registry.ordered():
        assert registry.flows_to_cloud(entrada.entity_type), entrada.entity_type
        assert registry.flows_to_local(entrada.entity_type), entrada.entity_type
