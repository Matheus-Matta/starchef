"""As periódicas não podem acumular nem prender o worker.

Na nuvem de produção (out/2026) a CPU ficou presa em 300% e o painel passou a
responder em 1,5 s. Eram duas falhas somadas:

* o beat enfileira a cada 5–15 s, e sem `expires` cada tique atrasado ficava
  esperando a vez: 1.034 + 919 + 288 tiques velhos na fila, o worker rodando
  sem parar tarefas vencidas que não achavam nada para fazer;
* `sync.notify_pending_to_local_nodes` chamava o `group_send` sem prazo, e um
  envio travado segurava o processo os 30 minutos do limite global, até o
  SIGKILL.
"""
import asyncio
import copy
import time

import pytest
from django.conf import settings

from apps.synchronization.tasks import dispatch
from config.settings.agenda import com_prazo
from config.settings.sync import SYNC_BEAT_SCHEDULE


def _sem_prazo(agenda):
    return [
        nome for nome, entrada in agenda.items()
        if isinstance(entrada["schedule"], (int, float))
        and not (0 < entrada.get("options", {}).get("expires", 0) <= entrada["schedule"])
    ]


def test_toda_periodica_do_beat_vence_antes_do_proximo_tique():
    assert _sem_prazo(settings.CELERY_BEAT_SCHEDULE) == []


def test_as_periodicas_da_sincronizacao_tambem_vencem():
    """Elas só entram no beat com SYNC_ENABLED — o teste não depende disso."""
    assert _sem_prazo(com_prazo(copy.deepcopy(SYNC_BEAT_SCHEDULE))) == []


def test_prazo_escrito_a_mao_nao_e_sobrescrito():
    agenda = com_prazo({"x": {"task": "x", "schedule": 60.0, "options": {"expires": 5}}})
    assert agenda["x"]["options"]["expires"] == 5


def test_aviso_travado_desiste_no_prazo(monkeypatch):
    class CamadaTravada:
        async def group_send(self, _grupo, _mensagem):
            await asyncio.sleep(3600)

    monkeypatch.setattr(dispatch, "PRAZO_DO_AVISO", 0.2)
    inicio = time.monotonic()
    assert dispatch._avisar(CamadaTravada(), "sync.no.1") is False
    assert time.monotonic() - inicio < 5


def test_aviso_que_responde_conta_como_enviado():
    enviados = []

    class Camada:
        async def group_send(self, grupo, mensagem):
            enviados.append(grupo)

    assert dispatch._avisar(Camada(), "sync.no.1") is True
    assert enviados == ["sync.no.1"]


@pytest.mark.parametrize("limite", ["time_limit", "soft_time_limit"])
def test_o_aviso_nunca_usa_o_limite_global_de_30_minutos(limite):
    assert getattr(dispatch.notify_pending_to_local_nodes, limite) <= 120
