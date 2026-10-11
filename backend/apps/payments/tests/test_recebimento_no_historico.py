"""O recebimento ignorado (reenvio, versão mais velha) fica no histórico.

Ignorar é o certo — o UUID já existe e a versão gravada é mais nova —, mas o
que chegou é guardado em `SyncDiscard` para dar para recuperar.
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.payments.tests.test_payment_service_card_subtype import (  # noqa: F401 — fixtures
    card_method, payable_order,
)
from apps.payments.tests.test_recebimento_por_uuid import _receber

pytestmark = pytest.mark.django_db


def test_versao_velha_e_reenvio_do_recebimento_vao_ao_historico(
    payable_order, card_method, manager_user  # noqa: F811
):
    """Ignorados, mas guardados: dá para recuperar o que chegou."""
    from apps.synchronization.models import SyncDiscard

    pid, agora = uuid.uuid4(), timezone.now()
    _receber(payable_order, card_method, manager_user, pid, agora, valor="5.00")
    _receber(payable_order, card_method, manager_user, pid, agora, valor="5.00")
    _receber(payable_order, card_method, manager_user, pid, agora - timedelta(seconds=5), valor="2.00")

    motivos = list(SyncDiscard.objects.filter(entity_id=str(pid)).order_by("created_at")
                   .values_list("motivo", "origem"))
    assert motivos == [(SyncDiscard.MOTIVO_REENVIO, SyncDiscard.ORIGEM_API),
                       (SyncDiscard.MOTIVO_VERSAO_MAIS_VELHA, SyncDiscard.ORIGEM_API)]
    velha = SyncDiscard.objects.get(entity_id=str(pid), motivo=SyncDiscard.MOTIVO_VERSAO_MAIS_VELHA)
    assert velha.dados["amount"] == "2.00" and velha.usuario_id == manager_user.pk


def test_uuid_que_chegou_pela_sincronizacao_no_mesmo_instante_devolve_o_existente(
    payable_order, card_method, manager_user, monkeypatch  # noqa: F811
):
    """O mesmo par de corridas da anotação: o recebimento chegava pela
    sincronização entre a consulta e a inserção, e o caixa via "valor
    duplicado" de um recebimento que existe. Agora é reenvio — e vai ao histórico."""
    from apps.payments.models import Payment
    from apps.synchronization.models import SyncDiscard

    pid, agora = uuid.uuid4(), timezone.now()
    primeiro = _receber(payable_order, card_method, manager_user, pid, agora)
    monkeypatch.setattr("apps.payments.recebimento_por_uuid.conciliar", lambda *a, **k: (None, False))
    payable_order.refresh_from_db()
    payable_order.payment_status = "partial"  # como estava antes de a cópia chegar
    payable_order.save(update_fields=["payment_status"])

    segundo = _receber(payable_order, card_method, manager_user, pid, agora)

    assert segundo.pk == primeiro.pk
    assert Payment.all_objects.filter(order=payable_order).count() == 1
    assert SyncDiscard.objects.filter(entity_id=str(pid), motivo=SyncDiscard.MOTIVO_REENVIO).exists()
