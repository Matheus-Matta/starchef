"""A exclusão também obedece à regra do mais novo.

* Um DELETE atrasado apagava a linha mesmo quando ela tinha sido editada
  DEPOIS — a edição mais nova sumia.
* Um UPSERT atrasado de uma linha apagada aqui não encontrava nada e
  INSERIA: a linha excluída voltava, com o dado velho.
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, crypto, serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db

_sequencia = iter(range(5_000, 10_000))


def _versao(momento):
    return int(momento.timestamp() * 1_000_000)


@pytest.fixture
def restaurante(conta):
    from apps.restaurants.models import Restaurant

    return Restaurant.objects.create(account=conta, legal_name="E LTDA", trade_name="E")


def _grupo(conta, restaurante, **campos):
    from apps.customers.models import CustomerGroup

    return CustomerGroup(account=conta, restaurant=restaurante, name="Grupo", **campos)


def _evento(conta, origem, destino, instancia, *, quando, operacao, direcao=Direction.INBOUND,
            status=EventStatus.RECEIVED):
    instancia.updated_at = quando
    instancia.created_at = instancia.created_at or quando
    payload = serialization.build_payload(
        instancia, registry.require("customer_group"), origin_node_id=origem.id
    )
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino, direction=direcao,
        sequence=next(_sequencia), entity_type="customer_group",
        entity_id=payload["entity_id"], operation=operacao,
        entity_version=payload["entity_version"], payload=payload,
        payload_checksum=crypto.checksum(payload), status=status,
    )


def _existe(pk):
    from apps.customers.models import CustomerGroup

    return CustomerGroup._base_manager.filter(pk=pk, deleted_at__isnull=True).exists()


def test_exclusao_mais_antiga_que_a_edicao_local_nao_apaga(
    como_loja, conta, no_nuvem, no_loja, restaurante
):
    from apps.core.tenant import tenant_context

    with tenant_context(conta):
        grupo = _grupo(conta, restaurante)
        grupo.save()
    editado = timezone.now() + timedelta(minutes=5)
    type(grupo)._base_manager.filter(pk=grupo.pk).update(updated_at=editado)

    evento = _evento(conta, no_nuvem, no_loja, _grupo(conta, restaurante, id=grupo.pk),
                     quando=editado - timedelta(minutes=1), operacao=Operation.DELETE)
    apply.apply_event(evento)

    assert _existe(grupo.pk)


def test_versao_antiga_nao_ressuscita_linha_apagada_aqui(
    como_loja, conta, no_nuvem, no_loja, restaurante
):
    pk = uuid.uuid4()
    apagado = timezone.now()
    # A lápide: a exclusão que esta loja gravou e mandou para a nuvem.
    _evento(conta, no_loja, no_nuvem, _grupo(conta, restaurante, id=pk), quando=apagado,
            operacao=Operation.DELETE, direcao=Direction.OUTBOUND, status=EventStatus.SENT)

    atrasado = _evento(conta, no_nuvem, no_loja, _grupo(conta, restaurante, id=pk),
                       quando=apagado - timedelta(seconds=10), operacao=Operation.UPSERT)
    apply.apply_event(atrasado)

    assert not _existe(pk)


def test_versao_mais_nova_que_a_exclusao_recria(
    como_loja, conta, no_nuvem, no_loja, restaurante
):
    """A regra é a mesma nos dois sentidos: editado DEPOIS de apagado, volta."""
    pk = uuid.uuid4()
    apagado = timezone.now()
    _evento(conta, no_loja, no_nuvem, _grupo(conta, restaurante, id=pk), quando=apagado,
            operacao=Operation.DELETE, direcao=Direction.OUTBOUND, status=EventStatus.SENT)

    depois = _evento(conta, no_nuvem, no_loja, _grupo(conta, restaurante, id=pk),
                     quando=apagado + timedelta(seconds=10), operacao=Operation.UPSERT)
    apply.apply_event(depois)

    assert _existe(pk)


def test_a_versao_da_exclusao_e_o_momento_em_que_ela_aconteceu(
    como_loja, conta, no_nuvem, restaurante
):
    """Editado às 10:00 e apagado às 15:00, a exclusão vale como 15:00."""
    from apps.core.tenant import tenant_context
    from apps.synchronization.services import outbox

    with tenant_context(conta):
        grupo = _grupo(conta, restaurante)
        grupo.save()
    antigo = timezone.now() - timedelta(hours=5)
    type(grupo)._base_manager.filter(pk=grupo.pk).update(updated_at=antigo)
    grupo.refresh_from_db()

    antes = _versao(timezone.now())
    [evento] = outbox.record_delete(grupo)

    assert evento.entity_version >= antes
    assert evento.payload["entity_version"] == evento.entity_version
