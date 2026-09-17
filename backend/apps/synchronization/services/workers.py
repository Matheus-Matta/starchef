"""Há alguém consumindo as filas da sincronização?

A falha que este módulo existe para denunciar é silenciosa, e por isso cara: as
tarefas do módulo declaram fila própria (`sync.apply`, `sync.bootstrap`, …), e
um worker Celery iniciado sem `-Q` consome **somente** a fila `celery`. As
tarefas do sync então são enfileiradas normalmente, ninguém as retira, e não há
erro em lugar nenhum — nem log, nem exceção, nem métrica.

O sintoma que chega é outro: a loja se matricula, conecta, e não recebe carga
nenhuma. Quem investiga vai olhar a conexão, o token, o proxy — tudo certo — e
perder horas antes de desconfiar do `-Q` do worker.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: `inspect` fala com os workers pelo broker e espera resposta. Sem teto, um
#: broker fora do ar trava o comando que deveria estar diagnosticando.
TIMEOUT = 3.0


def filas_esperadas():
    return set(getattr(settings, "SYNC_CELERY_QUEUES", ()))


def filas_consumidas(timeout=TIMEOUT):
    """As filas que os workers vivos declaram consumir.

    Devolve `None` quando não deu para perguntar (broker fora, nenhum worker) —
    que é diferente de "perguntei e a resposta foi nenhuma".
    """
    try:
        from config.celery import app

        respostas = app.control.inspect(timeout=timeout).active_queues()
    except Exception:  # noqa: BLE001 — diagnóstico nunca derruba quem chamou
        logger.debug("sync: não foi possível inspecionar os workers", exc_info=True)
        return None

    if not respostas:
        return None

    consumidas = set()
    for filas in respostas.values():
        consumidas.update(f.get("name") for f in (filas or []) if f.get("name"))
    return consumidas


def filas_orfas(timeout=TIMEOUT):
    """`(faltando, consumidas)` — filas do sync que ninguém está consumindo.

    `faltando` vazio com `consumidas=None` significa "não consegui verificar",
    não "está tudo certo". Quem chama precisa distinguir os dois.
    """
    consumidas = filas_consumidas(timeout=timeout)
    if consumidas is None:
        return set(), None
    return filas_esperadas() - consumidas, consumidas


def diagnostico(timeout=TIMEOUT):
    """Uma frase pronta para o operador, ou None quando está tudo certo."""
    faltando, consumidas = filas_orfas(timeout=timeout)
    if consumidas is None:
        return (
            "Não foi possível falar com nenhum worker Celery. Se a sincronização "
            "estiver ligada, confira se o container do worker está no ar."
        )
    if not faltando:
        return None
    return (
        f"{len(faltando)} fila(s) da sincronização sem worker consumindo: "
        + ", ".join(sorted(faltando))
        + ". As tarefas ficam enfileiradas para sempre, sem erro. "
        "Inicie o worker com `-Q celery,"
        + ",".join(sorted(filas_esperadas()))
        + "`."
    )
