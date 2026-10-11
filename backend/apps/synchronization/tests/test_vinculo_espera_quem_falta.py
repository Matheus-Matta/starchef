"""O vínculo com quem AINDA NÃO CHEGOU espera; com o que não existe aqui, ignora.

Achado no par Docker (`loadtest/dia_a_dia`): a estação de caixa chegou à loja
antes do operador vinculado a ela. O vínculo apontava para um usuário que
ainda não existia e era IGNORADO para sempre — o caixa recebia "o operador
não está vinculado a este caixa" até alguém salvar a estação de novo.

"Ignorar" foi pensado para o catálogo de permissões (provisionado por código,
NÃO sincroniza): a nuvem pode conhecer uma que a loja não tem. Usuário,
restaurante, produto SINCRONIZAM — faltar é estar a caminho: o evento volta
para a fila e é aplicado quando o usuário chegar.
"""
import uuid

import pytest
from django.contrib.auth.models import User

from apps.payments.models import CashStation
from apps.restaurants.models import Restaurant
from apps.synchronization.constants import EventStatus
from apps.synchronization.services import apply
from apps.synchronization.tests.test_apply import _evento

pytestmark = pytest.mark.django_db


def test_estacao_que_chega_antes_do_operador_espera_por_ele(como_loja, conta, no_nuvem, no_loja):
    restaurante = Restaurant.all_objects.create(account=conta, legal_name="R", trade_name="R")
    estacao_id = uuid.uuid4()
    evento = _evento(conta, no_nuvem, no_loja, entity_type="cash_station", entity_id=estacao_id,
                     fields={"account_id": str(conta.id), "restaurant_id": str(restaurante.id),
                             "name": "PDV 1", "code": "PDV-1", "is_active": True,
                             "cash_limit": "1000.00", "operators": ["sim.caixa1"]})

    apply.apply_event(evento)
    evento.refresh_from_db()
    assert evento.status != EventStatus.APPLIED  # esperando o operador, não perdido

    User.objects.create_user(username="sim.caixa1", password="x")  # o usuário chegou
    evento.status = EventStatus.RECEIVED
    evento.save(update_fields=["status"])
    apply.apply_event(evento)

    estacao = CashStation.all_objects.get(pk=estacao_id)
    assert list(estacao.operators.values_list("username", flat=True)) == ["sim.caixa1"]


def test_permissao_que_nao_existe_aqui_continua_ignorada(como_loja, conta, no_nuvem, no_loja):
    from apps.accounts.models import Role

    perfil_id = uuid.uuid4()
    evento = _evento(conta, no_nuvem, no_loja, entity_type="role", entity_id=perfil_id,
                     fields={"account_id": str(conta.id), "name": "Gerente X", "code": "gx",
                             "permissions": ["permissao.que.so.a.nuvem.tem"]})

    apply.apply_event(evento)

    assert Role.all_objects.filter(pk=perfil_id).exists()
