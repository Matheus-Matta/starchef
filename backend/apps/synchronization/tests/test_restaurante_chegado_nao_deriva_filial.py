"""O restaurante que CHEGA pela sincronização não cria filial na loja.

Achado no teste de emissão da ACBrLib no par Docker: o `post_save` do
Restaurant deriva a filial única (`sync_branch_for_restaurant`). Aplicado o
restaurante vindo da nuvem, a loja criava uma filial com UUID PRÓPRIO — e a
filial verdadeira chegava logo depois, com outro UUID. Duas filiais. Na
próxima edição do restaurante na nuvem, a loja tentava renomear a primeira
para o nome da segunda e batia em `unique_branch_name_by_restaurant`: o evento
falhava para sempre e travava a fila daquele restaurante.
"""
import time
import uuid

import pytest

from apps.restaurants.models import Branch
from apps.synchronization.services import apply
from apps.synchronization.tests.test_apply import _evento

pytestmark = pytest.mark.django_db


def test_restaurante_aplicado_nao_cria_filial_e_a_da_nuvem_e_a_unica(como_loja, conta, no_nuvem, no_loja):
    restaurante_id, filial_id = uuid.uuid4(), uuid.uuid4()
    campos = {"account_id": str(conta.id), "legal_name": "Burger LTDA",
              "trade_name": "Burger Palace", "is_active": True}
    apply.apply_event(_evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                              entity_id=restaurante_id, fields=campos, sequence=1))
    assert not Branch.all_objects.filter(restaurant_id=restaurante_id).exists()

    apply.apply_event(_evento(conta, no_nuvem, no_loja, entity_type="branch", entity_id=filial_id,
                              sequence=2, fields={"account_id": str(conta.id),
                                                  "restaurant_id": str(restaurante_id),
                                                  "name": "Burger Palace", "is_active": True}))
    # A edição seguinte do restaurante na nuvem não pode tropeçar numa filial local.
    assert apply.apply_event(_evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                                     entity_id=restaurante_id, sequence=3, version=int(time.time() * 1_000_000) + 60_000_000,
                                     fields={**campos, "phone": "1133334444"})) is True
    assert list(Branch.all_objects.filter(restaurant_id=restaurante_id).values_list("id", flat=True)) == [filial_id]


def test_restaurante_aplicado_nao_cria_formas_de_pagamento_locais(como_loja, conta, no_nuvem, no_loja):
    """Mesma família, achada no par Docker: o `post_save` do Restaurant cria as
    formas de pagamento padrão. Aplicado o restaurante vindo da nuvem, a loja
    criava quatro formas com UUID próprio — e, criadas DENTRO do apply, nenhuma
    virava evento: ficavam só na loja para sempre, e um recebimento com uma
    delas nunca seria aplicado na nuvem. As formas da nuvem chegam sozinhas."""
    from apps.payments.models import PaymentMethod

    restaurante_id = uuid.uuid4()
    apply.apply_event(_evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                              entity_id=restaurante_id, sequence=1,
                              fields={"account_id": str(conta.id), "legal_name": "P LTDA",
                                      "trade_name": "Pizza", "is_active": True}))

    assert not PaymentMethod.all_objects.filter(restaurant_id=restaurante_id).exists()
