"""Duas "rodada 2" da mesma comanda, uma de cada lado, não travam a fila.

Com o terminal alternando entre loja e nuvem, cada lado numera a rodada de
cozinha da comanda por conta própria (`max + 1`). As duas nascem "rodada 2", e o
índice único (comanda, número) recusava a segunda na sincronização: virava
conflito, a rodada nunca era aplicada e os itens dela ficavam esperando para
sempre — atrás deles os itens do pedido e o estoque. No par real
(`loadtest/dia_a_dia`) foram 205 conflitos e a fila não assentou.

A regra é a mesma nos dois lados, para os dois terminarem iguais: a rodada de
id MENOR fica com o número; a outra vai para o próximo livre, e essa mudança
vira evento para o outro lado.
"""
import uuid

import pytest
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, crypto, serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db

MENOR = uuid.UUID("00000000-0000-4000-8000-000000000001")
MAIOR = uuid.UUID("ffffffff-ffff-4fff-bfff-ffffffffffff")


@pytest.fixture
def comanda(conta):
    from apps.core.tenant import tenant_context
    from apps.restaurants.models import Command, Restaurant

    restaurante = Restaurant.objects.create(account=conta, legal_name="C LTDA", trade_name="C")
    with tenant_context(conta):
        return Command.objects.create(account=conta, restaurant=restaurante, number=7)


def _rodada(comanda, pk, numero):
    from apps.orders.models_command_item import CommandBatch

    return CommandBatch(id=pk, account=comanda.account, restaurant=comanda.restaurant,
                        command=comanda, batch_number=numero, sent_at=timezone.now())


def _chega_da_nuvem(conta, no_nuvem, no_loja, rodada):
    rodada.created_at = rodada.updated_at = timezone.now()
    payload = serialization.build_payload(rodada, registry.require("command_batch"),
                                          origin_node_id=no_nuvem.id)
    evento = SyncEvent.objects.create(
        account=conta, source_node=no_nuvem, target_node=no_loja, direction=Direction.INBOUND,
        sequence=777, entity_type="command_batch", entity_id=str(rodada.pk),
        operation=Operation.UPSERT, entity_version=payload["entity_version"], payload=payload,
        payload_checksum=crypto.checksum(payload), status=EventStatus.RECEIVED,
    )
    apply.apply_event(evento)
    evento.refresh_from_db()
    return evento


def _numeros(comanda):
    from apps.orders.models_command_item import CommandBatch

    return dict(CommandBatch._base_manager.filter(command=comanda).values_list("id", "batch_number"))


@pytest.mark.parametrize(("local_id", "remoto_id"), [(MAIOR, MENOR), (MENOR, MAIOR)])
def test_a_rodada_de_id_menor_fica_com_o_numero(como_loja, conta, no_nuvem, no_loja, comanda,
                                                 local_id, remoto_id):
    from apps.synchronization.models import SyncConflict

    _rodada(comanda, local_id, 2).save()
    evento = _chega_da_nuvem(conta, no_nuvem, no_loja, _rodada(comanda, remoto_id, 2))

    numeros = _numeros(comanda)
    assert numeros == {MENOR: 2, MAIOR: 3}
    assert evento.status == EventStatus.APPLIED
    assert not SyncConflict.objects.filter(entity_type="command_batch").exists()
    # A renumeração viaja para o outro lado, senão lá a rodada continuaria "2".
    assert SyncEvent.objects.filter(direction=Direction.OUTBOUND, entity_type="command_batch",
                                    entity_id=str(MAIOR), payload__fields__batch_number=3).exists()


def test_atualizacao_que_leva_ao_numero_ocupado_tambem_renumera(
    como_loja, conta, no_nuvem, no_loja, comanda
):
    """A outra ponta mudou o número de uma rodada que já existe aqui para um
    número que outra rodada daqui ocupa: a atualização batia na trava única e
    ficava retentando para sempre."""
    _rodada(comanda, MENOR, 2).save()
    _rodada(comanda, MAIOR, 3).save()

    evento = _chega_da_nuvem(conta, no_nuvem, no_loja, _rodada(comanda, MAIOR, 2))

    numeros = _numeros(comanda)
    assert numeros[MENOR] == 2
    assert numeros[MAIOR] not in (2,)
    assert evento.status == EventStatus.APPLIED
