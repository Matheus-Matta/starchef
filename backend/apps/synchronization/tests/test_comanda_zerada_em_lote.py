"""O zerar da nuvem chegando à loja EM LOTE — e pelo caminho real do worker.

As regras de decisão estão em `test_comanda_zerada_na_nuvem.py`; aqui fica o
que só aparece com volume (a conferência custa duas consultas por lote, não
uma por evento) e o caminho de ponta a ponta.
"""
import uuid

import pytest
from django.utils import timezone

from apps.synchronization.constants import Direction, EventStatus, NodeType, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import conflicts, crypto
from apps.synchronization.tests.test_comanda_zerada_na_nuvem import (  # noqa: F401 — fixture
    _agora,
    _decidir,
    _Linha,
    _loja_sem_queda,
    _sequencia,
    _subiu,
)

pytestmark = pytest.mark.django_db


def test_retrato_do_lote_custa_duas_consultas_para_centenas_de_eventos(
    conta, no_loja, no_nuvem, django_assert_num_queries
):
    """Ação em massa é validada em lote: o zerar de 300 comandas não pode virar
    300 idas ao banco para decidir conflito."""
    from apps.synchronization.services import comanda_conflicts

    linhas = [_Linha(uuid.uuid4()) for _ in range(300)]
    local = _agora() - 9_000_000
    for linha in linhas[:3]:
        _subiu(conta, no_loja, no_nuvem, "command_item", linha, versao=local,
               status=EventStatus.ACKNOWLEDGED)
    eventos = [type("E", (), {"entity_type": "command_item", "entity_id": str(l.pk)})()
               for l in linhas]

    with django_assert_num_queries(2):
        with comanda_conflicts.lote(eventos):
            respostas = {
                comanda_conflicts.nuvem_ja_conhece_a_versao_local(
                    "command_item", NodeType.LOCAL, linha, local)
                for linha in linhas
            }
    assert respostas == {True}


def test_mesmo_item_duas_vezes_no_lote_nao_vira_conflito(conta, no_loja, no_nuvem):
    """Cancelado e depois encerrado: a 2ª versão é julgada sabendo da 1ª."""
    from datetime import timedelta

    from apps.synchronization.services import comanda_conflicts

    linha = _Linha(uuid.uuid4())
    evento = type("E", (), {"entity_type": "command_item", "entity_id": str(linha.pk),
                            "applied_at": timezone.now() + timedelta(seconds=1)})()
    with comanda_conflicts.lote([evento]):
        # A 1ª aplicação gravou a linha "agora" (save do apply).
        comanda_conflicts.anotar_aplicado(evento)
        local = _agora()
        assert _decidir("command_item", linha, local=local, remoto=local + 5_000_000) == (
            conflicts.APLICAR
        )


def test_linha_recebida_da_nuvem_e_editada_de_novo_por_ela_aplica(conta, no_loja, no_nuvem):
    """O `save` do apply dá à linha a versão "agora"; o `applied_at` do evento
    de entrada a cobre. Sem isso, a SEGUNDA edição da nuvem virava conflito."""
    linha = _Linha(uuid.uuid4())
    aplicado = timezone.now()
    payload = {"fields": {}}
    SyncEvent.objects.create(
        account=conta, source_node=no_nuvem, target_node=no_loja,
        direction=Direction.INBOUND, sequence=next(_sequencia), entity_type="command",
        entity_id=str(linha.pk), operation=Operation.UPSERT, entity_version=1,
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.APPLIED, applied_at=aplicado,
    )
    local = int(aplicado.timestamp() * 1_000_000) - 1000

    assert _decidir("command", linha, local=local, remoto=_agora() + 1) == conflicts.APLICAR


def test_ponta_a_ponta_a_comanda_limpa_na_nuvem_chega_limpa_a_loja(conta, no_loja, no_nuvem):
    """A comanda nasce na loja, sobe, a nuvem confirma; o painel limpa o cartão
    na nuvem e o lote desce pelo worker de verdade. Antes: conflito aberto e a
    loja com o nome do cliente; agora: aplicado."""
    from datetime import timedelta

    from apps.restaurants.models import Branch, Command, Restaurant
    from apps.synchronization import worker_steps
    from apps.synchronization.models import SyncConflict
    from apps.synchronization.services import dispatch, serialization
    from apps.synchronization.services.registry import registry

    restaurante = Restaurant.objects.create(account=conta, legal_name="R LTDA", trade_name="R")
    filial = Branch.all_objects.filter(restaurant=restaurante).first()
    comanda = Command.objects.create(
        account=conta, restaurant=restaurante, branch=filial, number=7, customer_name="João",
    )
    lote, _ = dispatch.collect_batch(no_loja)
    dispatch.mark_sent(lote)
    worker_steps.tratar_ack({"acknowledged": [str(e.event_id) for e in lote]}, str(no_nuvem.id))

    campos = serialization.serialize(comanda, registry.get("command"))
    campos["customer_name"] = ""
    versao = int((comanda.updated_at + timedelta(minutes=5)).timestamp() * 1_000_000)
    payload = {"schema_version": 1, "entity_type": "command", "entity_id": str(comanda.pk),
               "entity_version": versao, "origin_node_id": str(no_nuvem.id), "fields": campos}
    bruto = {
        "event_id": str(uuid.uuid4()), "account_id": str(conta.id),
        "target_node_id": str(no_loja.id), "sequence": 900, "entity_type": "command",
        "entity_id": str(comanda.pk), "operation": "UPSERT", "entity_version": versao,
        "payload": payload, "payload_checksum": crypto.checksum(payload),
    }
    ids = worker_steps.registrar_lote_recebido({"events": [bruto]}, str(no_nuvem.id))

    assert len(worker_steps.aplicar_recebidos(ids)) == 1
    comanda.refresh_from_db()
    assert comanda.customer_name == ""
    assert not SyncConflict.objects.filter(entity_id=str(comanda.pk)).exists()
