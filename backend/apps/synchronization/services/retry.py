"""Backoff, jitter e a fronteira entre "tenta de novo" e "desistiu".

A escada é a do plano (§18): imediata, 5s, 15s, 30s, 1min, depois exponencial
até o teto. O jitter existe para que cem lojas que perderam a mesma internet
não voltem todas no mesmo segundo.
"""
import random

from django.utils import timezone

from apps.synchronization.constants import EventStatus

#: Segundos até cada tentativa, a partir da segunda.
ESCADA = [0, 5, 15, 30, 60]
TETO_SEGUNDOS = 600
#: Depois disto o evento vira DEAD — e continua no banco, com payload e erro.
MAX_TENTATIVAS = 12
JITTER = 0.25


def delay_for(attempts):
    """Segundos até a próxima tentativa, já com jitter."""
    if attempts < len(ESCADA):
        base = ESCADA[attempts]
    else:
        base = min(TETO_SEGUNDOS, ESCADA[-1] * (2 ** (attempts - len(ESCADA) + 1)))
    if base <= 0:
        return 0
    return base * (1 + random.uniform(-JITTER, JITTER))


def next_attempt_at(attempts):
    return timezone.now() + timezone.timedelta(seconds=delay_for(attempts))


def mark_failure(event, erro, *, save=True):
    """Contabiliza a falha e decide entre FAILED (tenta de novo) e DEAD.

    DEAD não apaga nada: o payload e o último erro continuam gravados para o
    reprocessamento manual e para a carga total (§18).
    """
    event.attempts += 1
    event.last_error = str(erro)[:2000]
    if event.attempts >= MAX_TENTATIVAS:
        event.status = EventStatus.DEAD
        event.next_attempt_at = None
    else:
        event.status = EventStatus.FAILED
        event.next_attempt_at = next_attempt_at(event.attempts)
    if save:
        event.save(update_fields=["attempts", "last_error", "status", "next_attempt_at"])
    return event


def revive(event, *, save=True):
    """Traz um DEAD de volta para a fila. É o "Reprocessar falhas" do Admin."""
    event.status = EventStatus.PENDING
    event.attempts = 0
    event.next_attempt_at = None
    event.last_error = ""
    if save:
        event.save(update_fields=["status", "attempts", "next_attempt_at", "last_error"])
    return event
