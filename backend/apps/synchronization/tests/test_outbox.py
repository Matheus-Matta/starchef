"""A outbox grava junto com o dado, e o que não saiu continua guardado."""
import pytest
from django.db import transaction

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import outbox, recovery

pytestmark = pytest.mark.django_db


def _restaurante(conta, nome="Loja 1"):
    return Restaurant.objects.create(
        account=conta, legal_name=f"{nome} LTDA", trade_name=nome, is_active=True
    )


def test_gravar_o_dado_gera_o_evento(como_nuvem, conta, no_loja):
    _restaurante(conta)
    evento = SyncEvent.objects.get(entity_type="restaurant")
    assert evento.direction == Direction.OUTBOUND
    assert evento.status == EventStatus.PENDING
    assert evento.target_node_id == no_loja.id
    assert evento.payload["fields"]["trade_name"] == "Loja 1"


def test_rollback_do_dado_desfaz_o_evento(como_nuvem, conta):
    """O ponto do §11.1: os dois vivem e morrem na MESMA transação."""
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            _restaurante(conta, "Vai sumir")
            raise RuntimeError("falha no meio da operação")

    assert not Restaurant.all_objects.filter(trade_name="Vai sumir").exists()
    assert not SyncEvent.objects.filter(entity_type="restaurant").exists()


def test_evento_nao_confirmado_sobrevive_e_e_recuperavel(como_nuvem, conta):
    _restaurante(conta)
    evento = SyncEvent.objects.get(entity_type="restaurant")

    # Simula doze falhas: o evento morre, mas NÃO some.
    from apps.synchronization.services import retry

    for _ in range(retry.MAX_TENTATIVAS):
        retry.mark_failure(evento, "nuvem inacessível")
    evento.refresh_from_db()

    assert evento.status == EventStatus.DEAD
    assert evento.payload["fields"]["trade_name"] == "Loja 1"  # payload intacto
    assert evento.last_error == "nuvem inacessível"

    assert recovery.requeue([evento]) == 1
    evento.refresh_from_db()
    assert evento.status == EventStatus.PENDING
    assert evento.attempts == 0


def test_retencao_nao_apaga_o_que_nao_foi_confirmado(como_nuvem, conta):
    from django.utils import timezone

    _restaurante(conta)
    evento = SyncEvent.objects.get(entity_type="restaurant")
    SyncEvent.objects.filter(pk=evento.pk).update(
        status=EventStatus.DEAD, created_at=timezone.now() - timezone.timedelta(days=400)
    )
    assert recovery.prune(dias=30) == 0
    assert SyncEvent.objects.filter(pk=evento.pk).exists()


def test_retencao_apaga_o_que_ja_foi_confirmado(como_nuvem, conta):
    from django.utils import timezone

    _restaurante(conta)
    antigo = timezone.now() - timezone.timedelta(days=400)
    total = SyncEvent.objects.count()
    SyncEvent.objects.update(status=EventStatus.ACKNOWLEDGED, acknowledged_at=antigo)
    assert recovery.prune(dias=30) == total
    assert SyncEvent.objects.count() == 0


def test_aplicar_evento_remoto_nao_gera_evento_de_volta(como_loja, conta):
    """Sem isto, cada produto vindo da nuvem voltaria para a nuvem (§13.2)."""
    with outbox.applying_remote_event():
        _restaurante(conta, "Veio da nuvem")
    assert SyncEvent.objects.count() == 0


def test_instalacao_sem_no_configurado_nao_quebra_a_gravacao(settings, conta):
    """A loja tem de vender mesmo sem sincronização instalada."""
    settings.SYNC_NODE_ID = ""
    from apps.synchronization.services import nodes

    nodes.invalidate_cache()
    _restaurante(conta, "Sem sincronização")
    assert Restaurant.all_objects.filter(trade_name="Sem sincronização").exists()
    assert SyncEvent.objects.count() == 0


def test_sequencia_e_crescente_e_unica_por_origem(como_nuvem, conta):
    for indice in range(5):
        _restaurante(conta, f"Loja {indice}")
    sequencias = list(
        SyncEvent.objects.filter(entity_type="restaurant").order_by("sequence")
        .values_list("sequence", flat=True)
    )
    assert sequencias == sorted(sequencias)
    assert len(set(sequencias)) == len(sequencias)


def test_entidade_que_so_sobe_nao_desce(como_nuvem, conta, no_loja):
    """`order` é local_to_cloud: a nuvem não gera evento de pedido para a loja."""
    from apps.synchronization.services.registry import registry

    assert not registry.flows_to_local("order")
    assert registry.flows_to_cloud("order")


def test_delete_vira_evento_de_exclusao(como_nuvem, conta):
    restaurante = _restaurante(conta, "Vai fechar")
    SyncEvent.objects.all().delete()
    restaurante.delete()
    # Restaurant usa soft delete: a exclusão chega como UPDATE do deleted_at.
    evento = SyncEvent.objects.filter(entity_type="restaurant").latest("created_at")
    assert evento.operation in (Operation.UPDATE, Operation.DELETE)
