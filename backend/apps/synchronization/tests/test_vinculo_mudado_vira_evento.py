"""Mudar só o VÍNCULO (ManyToMany) também chega ao outro lado.

O vínculo viaja dentro do evento do pai (`m2m_fields`), e o evento só nascia
quando o pai era SALVO. `estacao.operators.set([caixa])` não salva a estação:
o vínculo mudava na nuvem e a loja nunca sabia. No par real
(`loadtest/dia_a_dia`), os três caixas recusados na loja com "O operador não
está vinculado a este caixa" — a estação tinha chegado, o operador não.
"""
import pytest
from django.contrib.auth import get_user_model

from apps.synchronization.constants import Direction
from apps.synchronization.models import SyncEvent

pytestmark = pytest.mark.django_db


def test_trocar_o_operador_da_estacao_gera_evento_com_o_vinculo(como_nuvem, conta, no_loja):
    from apps.core.tenant import tenant_context
    from apps.payments.models import CashStation
    from apps.restaurants.models import Restaurant

    restaurante = Restaurant.objects.create(account=conta, legal_name="E LTDA", trade_name="E")
    operador = get_user_model().objects.create_user("caixa.um", "c@t.test", "x")
    with tenant_context(conta):
        estacao = CashStation.objects.create(account=conta, restaurant=restaurante, name="PDV 1")
    antes = SyncEvent.objects.filter(entity_type="cash_station").count()

    estacao.operators.set([operador])

    eventos = SyncEvent.objects.filter(
        direction=Direction.OUTBOUND, target_node=no_loja, entity_type="cash_station",
        entity_id=str(estacao.pk),
    ).order_by("sequence")
    assert eventos.count() == antes + 1
    ultimo = eventos.last()
    assert ultimo.payload["fields"]["operators"] == ["caixa.um"]
    assert ultimo.entity_version > eventos.first().entity_version
