"""Aplicação de evento: idempotência, ordem e conflito (§23.2, §23.3)."""
import uuid

import pytest

from apps.restaurants.models import Branch, Restaurant
from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncConflict, SyncEvent
from apps.synchronization.services import apply, crypto

pytestmark = pytest.mark.django_db


def _evento(conta, origem, destino, *, entity_type, entity_id, fields,
            sequence=1, operation=Operation.UPSERT, version=10):
    payload = {
        "schema_version": 1,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "entity_version": version,
        "origin_node_id": str(origem.id),
        "fields": fields,
    }
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=sequence, entity_type=entity_type,
        entity_id=str(entity_id), operation=operation, entity_version=version,
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.RECEIVED,
    )


def test_aplica_registro_novo(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                     entity_id=restaurante_id,
                     fields={"account_id": str(conta.id), "legal_name": "Nova LTDA",
                             "trade_name": "Nova", "is_active": True})

    assert apply.apply_event(evento) is True
    assert Restaurant.all_objects.get(pk=restaurante_id).trade_name == "Nova"
    evento.refresh_from_db()
    assert evento.status == EventStatus.APPLIED


def test_mesmo_evento_duas_vezes_aplica_uma_vez(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                     entity_id=restaurante_id,
                     fields={"account_id": str(conta.id), "legal_name": "X LTDA",
                             "trade_name": "X", "is_active": True})
    apply.apply_event(evento)
    evento.refresh_from_db()

    # Segunda passada: não reaplica e não duplica.
    assert apply.apply_event(evento) is False
    assert Restaurant.all_objects.filter(pk=restaurante_id).count() == 1


def test_evento_repetido_nao_gera_registro_duplicado(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    campos = {"account_id": str(conta.id), "legal_name": "Y LTDA",
              "trade_name": "Y", "is_active": True}
    primeiro = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                       entity_id=restaurante_id, fields=campos, sequence=1)
    apply.apply_event(primeiro)

    # Reenvio depois de timeout: mesmo entity_id, sequência nova.
    segundo = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                      entity_id=restaurante_id, fields=campos, sequence=2, version=10)
    apply.apply_event(segundo)
    assert Restaurant.all_objects.filter(pk=restaurante_id).count() == 1


def test_dependencia_faltando_vira_retentativa_nao_perda(como_loja, conta, no_nuvem, no_loja):
    """Filial antes do restaurante: falha retentável, o evento continua lá."""
    evento = _evento(conta, no_nuvem, no_loja, entity_type="branch",
                     entity_id=uuid.uuid4(),
                     fields={"account_id": str(conta.id),
                             "restaurant_id": str(uuid.uuid4()),
                             "name": "Filial órfã"})

    assert apply.apply_event(evento) is False
    evento.refresh_from_db()
    assert evento.status == EventStatus.FAILED
    assert evento.next_attempt_at is not None
    assert "ainda não existe aqui" in evento.last_error
    assert evento.payload["fields"]["name"] == "Filial órfã"


def test_ordem_correta_aplica_os_dois(como_loja, conta, no_nuvem, no_loja):
    restaurante_id, filial_id = uuid.uuid4(), uuid.uuid4()
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
        fields={"account_id": str(conta.id), "legal_name": "Z LTDA",
                "trade_name": "Z", "is_active": True}, sequence=1))
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="branch", entity_id=filial_id,
        fields={"account_id": str(conta.id), "restaurant_id": str(restaurante_id),
                "name": "Matriz"}, sequence=2))

    assert Branch.all_objects.filter(pk=filial_id).exists()


def test_versao_mais_antiga_e_ignorada(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
        fields={"account_id": str(conta.id), "legal_name": "Atual LTDA",
                "trade_name": "Atual", "is_active": True}, version=10**18))

    atrasado = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                       entity_id=restaurante_id,
                       fields={"account_id": str(conta.id), "legal_name": "Velha LTDA",
                               "trade_name": "Velha", "is_active": True},
                       sequence=2, version=1)
    apply.apply_event(atrasado)
    assert Restaurant.all_objects.get(pk=restaurante_id).trade_name == "Atual"


def test_entidade_desconhecida_nao_derruba_nada(como_loja, conta, no_nuvem, no_loja):
    evento = _evento(conta, no_nuvem, no_loja, entity_type="entidade_do_futuro",
                     entity_id=uuid.uuid4(), fields={"x": 1})
    assert apply.apply_event(evento) is False
    evento.refresh_from_db()
    assert evento.status == EventStatus.APPLIED
    assert "não registrada" in evento.last_error


def test_dado_fiscal_divergente_vira_conflito(como_loja, conta, no_nuvem, no_loja, settings):
    """Nota fiscal nunca é resolvida em silêncio por last-write-wins (§15)."""
    from apps.synchronization.services import conflicts

    decisao = conflicts.decide(
        "invoice", local_version=5, remote_version=9,
        receiving_node_type="LOCAL", local_exists=True,
    )
    assert decisao == conflicts.CONFLITO


def test_conflito_registrado_guarda_as_duas_versoes(como_loja, conta, no_nuvem, no_loja):
    from apps.synchronization.services import conflicts

    evento = _evento(conta, no_nuvem, no_loja, entity_type="invoice",
                     entity_id=uuid.uuid4(), fields={"numero": "999"})
    conflicts.register(evento, local_instance=None, remote_payload={"numero": "999"},
                       local_version=5, remote_version=9)

    conflito = SyncConflict.objects.get(entity_type="invoice")
    assert conflito.local_version == 5 and conflito.remote_version == 9
    assert conflito.remote_payload == {"numero": "999"}
