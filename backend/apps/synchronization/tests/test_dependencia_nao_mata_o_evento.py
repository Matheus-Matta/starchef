"""Registro-pai que ainda não chegou não é motivo para desistir do filho.

O evento que chegava antes do pai ("aponta para X, que ainda não existe aqui")
gastava as 12 tentativas em cerca de uma hora e virava DEAD — e o dado nunca
mais chegava, nem quando o pai aparecia logo depois. Era o "dados não existem"
que só se resolvia com reprocessamento manual.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import retry

pytestmark = pytest.mark.django_db

ERRO = "OrderItem.order aponta para Order 1234, que ainda não existe aqui."


def _evento(conta, origem, destino, *, sequencia, **campos):
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=sequencia, entity_type="order_item",
        entity_id="1", operation=Operation.UPSERT, entity_version=1, payload={},
        payload_checksum="x", **campos,
    )


def test_falta_de_dependencia_nao_mata_o_evento_em_uma_hora(conta, no_nuvem, no_loja):
    evento = _evento(conta, no_nuvem, no_loja, sequencia=1, status=EventStatus.FAILED,
                     attempts=retry.MAX_TENTATIVAS - 1)

    retry.mark_failure(evento, ERRO, dependencia=True)

    assert evento.status == EventStatus.FAILED


def test_falta_de_dependencia_por_dias_vira_dead(conta, no_nuvem, no_loja):
    evento = _evento(conta, no_nuvem, no_loja, sequencia=2, status=EventStatus.FAILED,
                     attempts=retry.MAX_TENTATIVAS - 1)
    SyncEvent.objects.filter(pk=evento.pk).update(
        created_at=timezone.now() - retry.JANELA_DA_DEPENDENCIA - timedelta(hours=1)
    )
    evento.refresh_from_db()

    retry.mark_failure(evento, ERRO, dependencia=True)

    assert evento.status == EventStatus.DEAD


def test_outro_erro_continua_morrendo_nas_doze(conta, no_nuvem, no_loja):
    evento = _evento(conta, no_nuvem, no_loja, sequencia=3, status=EventStatus.FAILED,
                     attempts=retry.MAX_TENTATIVAS - 1)

    retry.mark_failure(evento, "erro qualquer")

    assert evento.status == EventStatus.DEAD


def test_dado_novo_acorda_quem_esperava_dependencia(como_loja, conta, no_nuvem, no_loja):
    daqui_a_dez = timezone.now() + timedelta(minutes=10)
    esperando = _evento(conta, no_nuvem, no_loja, sequencia=4, status=EventStatus.FAILED,
                        attempts=8, last_error=ERRO, next_attempt_at=daqui_a_dez)
    outro = _evento(conta, no_nuvem, no_loja, sequencia=5, status=EventStatus.FAILED,
                    attempts=8, last_error="erro de rede", next_attempt_at=daqui_a_dez)

    retry.acordar_quem_espera_dependencia(no_loja)

    esperando.refresh_from_db()
    outro.refresh_from_db()
    assert esperando.next_attempt_at is None
    assert outro.next_attempt_at == daqui_a_dez
