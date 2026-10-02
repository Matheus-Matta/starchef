"""O registro que chega pela sincronização mantém os horários de onde nasceu.

`auto_now_add`/`auto_now` trocam o horário recebido pelo de AGORA no INSERT:
um pedido aberto na nuvem às 12h aparecia na loja como aberto na hora em que
o evento chegou — e o relatório do turno mudava de dia.
"""
import uuid
from datetime import datetime, timezone

import pytest

from apps.restaurants.models import Restaurant
from apps.synchronization.services import apply
from apps.synchronization.tests.test_apply import _evento

pytestmark = pytest.mark.django_db

CRIADO = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
ALTERADO = datetime(2026, 9, 1, 12, 30, tzinfo=timezone.utc)


def test_insercao_preserva_criado_e_alterado_da_origem(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
                     fields={"account_id": str(conta.id), "legal_name": "Nova LTDA", "trade_name": "Nova",
                             "is_active": True, "created_at": CRIADO.isoformat(),
                             "updated_at": ALTERADO.isoformat()})

    assert apply.apply_event(evento) is True

    linha = Restaurant.all_objects.get(pk=restaurante_id)
    assert (linha.created_at, linha.updated_at) == (CRIADO, ALTERADO)


def test_sem_horario_no_payload_vale_o_de_agora(como_loja, conta, no_nuvem, no_loja):
    """Payload antigo, sem os campos: o INSERT segue como sempre foi."""
    restaurante_id = uuid.uuid4()
    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
                     fields={"account_id": str(conta.id), "legal_name": "Velha LTDA",
                             "trade_name": "Velha", "is_active": True})

    assert apply.apply_event(evento) is True

    linha = Restaurant.all_objects.get(pk=restaurante_id)
    assert linha.created_at > CRIADO and linha.updated_at is not None
