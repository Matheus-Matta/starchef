"""A nuvem aplica o que recebe SOZINHA, e diz que aplicou.

Aqui se enfileirava no Celery, com a garantia de que "o beat aplica na próxima
passada" se o enfileiramento falhasse. Só que o beat TAMBÉM é Celery: com os
workers fora do ar o enfileiramento tem SUCESSO — o Redis está bem —, a tarefa
fica parada na fila e nada nunca aplica.

Foi assim que 98 eventos de uma loja, pagamentos incluídos, ficaram gravados na
caixa de entrada e invisíveis no domínio, sem erro em lugar nenhum, até alguém
rodar a tarefa à mão no terminal.

Nenhum teste deste arquivo tem worker. É exatamente esse o ponto.
"""
import json
import uuid

import pytest

from apps.synchronization.constants import MessageType
from apps.synchronization.services import crypto, protocol
from apps.synchronization.tests.conftest import conectado, ler
from channels.db import database_sync_to_async

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]


async def test_a_nuvem_APLICA_sem_depender_de_worker(
    como_nuvem, conta, no_loja, no_nuvem
):
    """O defeito que custou 98 eventos parados, pagamentos incluídos.

    A aplicação era enfileirada no Celery, com a garantia de que "o beat
    aplica na próxima passada" se o enfileiramento falhasse. Só que o beat
    TAMBÉM é Celery: com os workers fora do ar o enfileiramento tem SUCESSO,
    a tarefa fica parada na fila e nada nunca aplica. O dado ficava gravado na
    caixa de entrada e invisível no domínio, sem erro em lugar nenhum, até
    alguém rodar a tarefa à mão no terminal.

    Aqui não existe worker nenhum — é o que este teste tem de especial.
    """
    from apps.restaurants.models import Restaurant

    com = await conectado(no_loja)
    await ler(com)

    cliente_id = str(uuid.uuid4())
    payload_evento = {
        "schema_version": 1, "entity_type": "restaurant", "entity_id": cliente_id,
        "entity_version": 5, "origin_node_id": str(no_loja.id),
        "fields": {
            "account_id": str(conta.id),
            "legal_name": "Da Fila LTDA",
            "trade_name": "Da Fila",
            "is_active": True,
        },
    }
    evento = {
        "event_id": str(uuid.uuid4()), "account_id": str(conta.id),
        "target_node_id": str(no_nuvem.id), "sequence": 1, "entity_type": "restaurant",
        "entity_id": cliente_id, "operation": "UPSERT",
        "entity_version": 5, "payload": payload_evento,
        "payload_checksum": crypto.checksum(payload_evento),
    }
    envelope = protocol.build(
        MessageType.EVENT_BATCH, source_node_id=no_loja.id, target_node_id=no_nuvem.id,
        account_id=conta.id, payload={"events": [evento]},
    )
    await com.send_to(text_data=json.dumps(envelope, default=str))
    await ler(com)  # o ACK de recebimento

    existe = await database_sync_to_async(
        Restaurant.all_objects.filter(pk=cliente_id).exists
    )()
    assert existe, "o evento foi guardado mas nunca chegou ao domínio"
    await com.disconnect()


async def test_a_nuvem_AVISA_que_aplicou(como_nuvem, conta, no_loja, no_nuvem):
    """A assimetria que fazia a fila mentir.

    A loja confirma a aplicação de volta (`acknowledged`); a nuvem só
    confirmava o RECEBIMENTO. Os eventos da loja ficavam em RECEIVED para
    sempre — um estado que não distingue "aplicado" de "perdido". Quem olhava
    a fila não tinha como saber qual dos dois era, e concluía o pior.
    """
    com = await conectado(no_loja)
    await ler(com)

    cliente_id = str(uuid.uuid4())
    payload_evento = {
        "schema_version": 1, "entity_type": "restaurant", "entity_id": cliente_id,
        "entity_version": 5, "origin_node_id": str(no_loja.id),
        "fields": {
            "account_id": str(conta.id),
            "legal_name": "Confirmada LTDA",
            "trade_name": "Confirmada",
            "is_active": True,
        },
    }
    evento_id = str(uuid.uuid4())
    evento = {
        "event_id": evento_id, "account_id": str(conta.id),
        "target_node_id": str(no_nuvem.id), "sequence": 1, "entity_type": "restaurant",
        "entity_id": cliente_id, "operation": "UPSERT",
        "entity_version": 5, "payload": payload_evento,
        "payload_checksum": crypto.checksum(payload_evento),
    }
    envelope = protocol.build(
        MessageType.EVENT_BATCH, source_node_id=no_loja.id, target_node_id=no_nuvem.id,
        account_id=conta.id, payload={"events": [evento]},
    )
    await com.send_to(text_data=json.dumps(envelope, default=str))

    primeiro_tipo, primeiro = await ler(com)
    segundo_tipo, segundo = await ler(com)

    assert primeiro_tipo == MessageType.ACK
    assert evento_id in primeiro["received"]
    assert segundo_tipo == MessageType.ACK
    assert segundo["acknowledged"] == [evento_id], (
        "sem isto a loja nunca sai de RECEIVED, aplicado ou não"
    )
    await com.disconnect()
