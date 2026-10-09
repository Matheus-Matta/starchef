"""A rede de segurança não desiste num erro passageiro do banco.

A marca da trigger é a última chance de uma gravação que escapou do signal
chegar ao outro lado. Ela era encerrada em QUALQUER falha — inclusive num
deadlock, que passa sozinho na tentativa seguinte. No par real
(`loadtest/dia_a_dia`) um item de comanda perdeu o evento pelo signal (deadlock
no contador) e depois pela rede (o mesmo deadlock): ficou na loja e nunca
chegou à nuvem, e o item do pedido que apontava para ele travou lá.
"""
import uuid

import pytest
from django.db import OperationalError
from django.utils import timezone

from apps.synchronization.models import SyncDirty
from apps.synchronization.services import dirty

pytestmark = pytest.mark.django_db


def _marca_de(conta):
    from apps.restaurants.models import Restaurant

    restaurante = Restaurant.objects.create(account=conta, legal_name="R LTDA", trade_name="R")
    return SyncDirty.objects.create(
        id=uuid.uuid4(), table_name=Restaurant._meta.db_table, row_id=str(restaurante.pk),
        operation="UPDATE", changed_at=timezone.now(),
    ), restaurante


def test_deadlock_deixa_a_marca_para_a_proxima_passada(como_loja, conta, no_nuvem, monkeypatch):
    marca, _ = _marca_de(conta)
    from apps.synchronization.services import outbox

    def trava(*_args, **_kwargs):
        raise OperationalError("deadlock detected")

    monkeypatch.setattr(outbox, "record", trava)
    monkeypatch.setattr(dirty, "_ja_tem_evento", lambda *_a: False)
    dirty.process()

    marca.refresh_from_db()
    assert marca.processed_at is None


def test_erro_que_nao_passa_sozinho_continua_encerrando(como_loja, conta, no_nuvem, monkeypatch):
    marca, _ = _marca_de(conta)
    from apps.synchronization.services import outbox

    def quebra(*_args, **_kwargs):
        raise ValueError("payload impossível")

    monkeypatch.setattr(outbox, "record", quebra)
    monkeypatch.setattr(dirty, "_ja_tem_evento", lambda *_a: False)
    dirty.process()

    marca.refresh_from_db()
    assert marca.processed_at is not None
    assert "payload impossível" in marca.error


def test_update_em_massa_depois_do_evento_na_mesma_transacao_vira_evento(como_loja, conta, no_nuvem):
    """O item foi criado (evento pelo signal) e, na MESMA transação, mudou de
    status por `QuerySet.update` — o envio para a cozinha faz exatamente isso.

    A marca da trigger leva o horário do INÍCIO da transação (`now()` do
    PostgreSQL), e o evento de criação nasce depois dele: a regra "existe
    evento criado depois da marca" dava a atualização como coberta, e o status
    novo nunca chegava à nuvem. No par real, todo item enviado à cozinha ficava
    `pending` lá e `sent` na loja.
    """
    from datetime import timedelta

    from apps.restaurants.models import Restaurant
    from apps.synchronization.models import SyncEvent

    inicio_da_transacao = timezone.now() - timedelta(seconds=1)
    restaurante = Restaurant.objects.create(account=conta, legal_name="K LTDA", trade_name="Antes")
    Restaurant.all_objects.filter(pk=restaurante.pk).update(
        trade_name="Depois", updated_at=timezone.now() + timedelta(seconds=1)
    )
    marca = SyncDirty.objects.create(
        id=uuid.uuid4(), table_name=Restaurant._meta.db_table, row_id=str(restaurante.pk),
        operation="UPDATE",
    )
    # `changed_at` é auto_now_add: o horário da trigger entra depois.
    SyncDirty.objects.filter(pk=marca.pk).update(changed_at=inicio_da_transacao)

    dirty.process()

    assert SyncEvent.objects.filter(
        entity_type="restaurant", entity_id=str(restaurante.pk),
        payload__fields__trade_name="Depois",
    ).exists()
