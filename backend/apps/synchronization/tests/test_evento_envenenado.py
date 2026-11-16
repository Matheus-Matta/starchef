"""Evento envenenado na fila de entrada: dado corrompido vindo do outro nó.

A loja aplica o que a nuvem manda (e vice-versa) sem passar pelos
serializers. Um evento estragado — versão antiga do app, bug do outro lado,
payload adulterado — não pode:

* derrubar a aplicação com exceção (o lote inteiro pararia);
* ser marcado como aplicado sem ter sido;
* travar a fila: o evento BOM que vem depois tem de entrar.
"""
import uuid

import pytest
from django.db import connection

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, crypto

pytestmark = pytest.mark.django_db


def _evento(conta, origem, destino, *, entity_type, entity_id, fields, sequence, payload_extra=None):
    payload = {
        "schema_version": 1, "entity_type": entity_type, "entity_id": str(entity_id),
        "entity_version": 10, "origin_node_id": str(origem.id), "fields": fields,
        **(payload_extra or {}),
    }
    checksum = crypto.checksum(payload)
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino, direction=Direction.INBOUND,
        sequence=sequence, entity_type=entity_type, entity_id=str(entity_id),
        operation=Operation.UPSERT, entity_version=10, payload=payload,
        payload_checksum=checksum, status=EventStatus.RECEIVED,
    )


def _restaurante(conta, **trocas):
    return {"account_id": str(conta.id), "legal_name": "Boa LTDA", "trade_name": "Boa",
            "is_active": True, **trocas}


VENENOS = {
    "campos-em-texto": {"entity_type": "restaurant", "fields": "legal_name=X"},
    "campos-nulos": {"entity_type": "restaurant", "fields": None},
    "tipo-de-entidade-desconhecido": {"entity_type": "foguete", "fields": {"x": 1}},
    "booleano-que-nao-e-booleano": {"entity_type": "restaurant", "fields": "__bool__"},
    # Só o Postgres impõe o tamanho do varchar; o SQLite grava qualquer texto.
    "texto-maior-que-a-coluna": {"entity_type": "restaurant", "fields": "__longo__"},
    "conta-de-outro-tenant": {"entity_type": "restaurant", "fields": "__outra_conta__"},
}
# Fora daqui de propósito: o checksum adulterado é barrado na CHEGADA
# (`inbox._gravar`), e isso já tem teste (`test_lote_isola_evento_ruim`).


@pytest.mark.parametrize("nome", list(VENENOS))
def test_evento_envenenado_nao_quebra_nem_trava_a_fila(nome, como_loja, conta, no_nuvem, no_loja):
    veneno = dict(VENENOS[nome])
    campos = veneno.pop("fields")
    alvo = uuid.uuid4()
    if campos == "__bool__":
        campos = _restaurante(conta, is_active="talvez")
    elif campos == "__longo__":
        campos = _restaurante(conta, legal_name="X" * 10_000)
    elif campos == "__outra_conta__":
        campos = _restaurante(conta, account_id=str(uuid.uuid4()))

    if nome == "texto-maior-que-a-coluna" and connection.vendor != "postgresql":
        pytest.skip("O SQLite não impõe o tamanho do varchar.")
    ruim = _evento(conta, no_nuvem, no_loja, entity_id=alvo, fields=campos, sequence=1, **veneno)

    try:
        aplicado = apply.apply_event(ruim)
    except Exception as exc:  # noqa: BLE001 — é exatamente o que o teste procura
        pytest.fail(f"{nome}: a aplicação levantou {type(exc).__name__}: {exc}")

    ruim.refresh_from_db()
    assert aplicado is False, f"{nome}: evento envenenado aplicado"
    if nome == "tipo-de-entidade-desconhecido":
        # §17: uma nuvem mais nova conhece entidades que a loja não. O evento é
        # dado por resolvido (sem mexer no domínio) para não travar a fila.
        assert ruim.status == EventStatus.APPLIED
    else:
        assert ruim.status != EventStatus.APPLIED
        assert ruim.last_error, f"{nome}: recusado sem motivo registrado"

    # O evento bom, logo atrás, entra normalmente.
    bom_id = uuid.uuid4()
    bom = _evento(conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=bom_id,
                  fields=_restaurante(conta, trade_name="Depois do veneno"), sequence=2)
    assert apply.apply_event(bom) is True
    assert Restaurant.all_objects.get(pk=bom_id).trade_name == "Depois do veneno"
