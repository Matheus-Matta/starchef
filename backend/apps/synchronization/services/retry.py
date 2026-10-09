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
#: Quanto tempo um evento pode esperar o registro-pai antes de virar DEAD.
#:
#: As 12 tentativas acabam em cerca de uma hora, e uma loja que ficou fora uma
#: tarde recebe o filho antes de o pai terminar de chegar. Esperar o pai não é
#: defeito do evento: ele segue tentando no teto da escada (10 minutos) por
#: estes dias, e é acordado na hora quando chega dado novo
#: (`acordar_quem_espera_dependencia`).
JANELA_DA_DEPENDENCIA = timezone.timedelta(days=3)
#: O texto com que `apply.DependencyMissing` descreve o pai ausente.
MARCA_DA_DEPENDENCIA = "ainda não existe aqui"


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


def mark_failure(event, erro, *, save=True, dependencia=False):
    """Contabiliza a falha e decide entre FAILED (tenta de novo) e DEAD.

    DEAD não apaga nada: o payload e o último erro continuam gravados para o
    reprocessamento manual e para a carga total (§18). `dependencia` é a falha
    de registro-pai ausente, que espera [JANELA_DA_DEPENDENCIA] em vez de
    morrer nas 12 tentativas.
    """
    event.attempts += 1
    event.last_error = str(erro)[:2000]
    if event.attempts >= MAX_TENTATIVAS and not (dependencia and _ainda_espera(event)):
        event.status = EventStatus.DEAD
        event.next_attempt_at = None
    else:
        event.status = EventStatus.FAILED
        event.next_attempt_at = next_attempt_at(event.attempts)
    if save:
        event.save(update_fields=["attempts", "last_error", "status", "next_attempt_at"])
    return event


def _ainda_espera(event):
    nasceu = getattr(event, "created_at", None)
    return nasceu is None or timezone.now() - nasceu < JANELA_DA_DEPENDENCIA


def acordar_quem_espera_dependencia(node):
    """Chegou dado novo: quem esperava o pai tenta de novo JÁ.

    Sem isto, o filho cujo pai acabou de chegar ficava até 10 minutos parado
    no teto da escada — o pedido aparece e os itens dele não.
    """
    from apps.synchronization.constants import Direction
    from apps.synchronization.models import SyncEvent

    return SyncEvent.objects.filter(
        direction=Direction.INBOUND, target_node=node, status=EventStatus.FAILED,
        last_error__contains=MARCA_DA_DEPENDENCIA,
    ).update(next_attempt_at=None)


def revive(event, *, save=True):
    """Traz um DEAD de volta para a fila. É o "Reprocessar falhas" do Admin."""
    event.status = EventStatus.PENDING
    event.attempts = 0
    event.next_attempt_at = None
    event.last_error = ""
    if save:
        event.save(update_fields=["status", "attempts", "next_attempt_at", "last_error"])
    return event
