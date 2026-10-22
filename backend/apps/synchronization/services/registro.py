"""O que a sincronização ENVIOU, RECEBEU, APLICOU e por que FALHOU — no log.

O log dizia só "15 evento(s) voltaram para a fila", a cada volta, sem dizer
quais nem por quê: para saber, era preciso entrar no servidor e rodar
`sync_status`. Agora cada passo deixa uma linha no logger `starchef.sync`:

    sync: ENVIADOS 3 evento(s) para Loja Centro — order×2, payment×1
    sync: RECEBIDOS 5 evento(s) de Loja Centro — commanditem×5
    sync: CONFIRMADOS por Loja Centro — 3 confirmado(s), 0 recebido(s), 0 recusado(s)
    sync: APLICADOS 5 evento(s) — commanditem×5
    sync: FALHOU payment/2f1c… (tentativa 3 de 12, próxima às 09:31:05) — Payment.order …

O resumo vai por tipo, e não evento a evento, para o log continuar legível
numa carga de mil eventos. A falha vai uma a uma: é ela que alguém precisa ler.
`DJANGO_LOG_LEVEL=DEBUG` mostra também os ids de cada lote.
"""
import logging
from collections import Counter

from django.utils import timezone

logger = logging.getLogger("starchef.sync")


def _tipo(evento):
    return evento.get("entity_type") if isinstance(evento, dict) else evento.entity_type


def _ids(eventos):
    return [str(e.get("event_id") if isinstance(e, dict) else e.event_id) for e in eventos]


def tipos(eventos):
    """`order×2, payment×1` — os tipos do lote, do mais frequente ao menos."""
    contagem = Counter(_tipo(e) or "?" for e in eventos)
    return ", ".join(f"{tipo}×{n}" for tipo, n in contagem.most_common())


def nome_do_no(no):
    if no is None:
        return "?"
    return getattr(no, "name", "") or str(getattr(no, "id", no))


def enviado(eventos, destino=None):
    if not eventos:
        return
    logger.info("sync: ENVIADOS %s evento(s) para %s — %s",
                len(eventos), nome_do_no(destino), tipos(eventos))
    logger.debug("sync: ids enviados %s", _ids(eventos))


def recebido(aceitos, recusados, origem):
    if not aceitos and not recusados:
        return
    logger.info("sync: RECEBIDOS %s evento(s) de %s — %s%s",
                len(aceitos), nome_do_no(origem), tipos(aceitos) or "nenhum novo",
                f" | {len(recusados)} RECUSADO(S)" if recusados else "")
    logger.debug("sync: ids recebidos %s", _ids(aceitos))


def confirmado(origem, confirmados, recebidos, falhos):
    if not (confirmados or recebidos or falhos):
        return
    nivel = logging.WARNING if falhos else logging.INFO
    logger.log(nivel, "sync: CONFIRMADOS por %s — %s confirmado(s), %s recebido(s), %s recusado(s)",
               nome_do_no(origem), len(confirmados), len(recebidos), len(falhos))


def aplicados(eventos):
    if eventos:
        logger.info("sync: APLICADOS %s evento(s) — %s", len(eventos), tipos(eventos))


def falhou(evento):
    """Depois de `retry.mark_failure`: o evento já tem tentativas, estado e erro."""
    from apps.synchronization.constants import EventStatus
    from apps.synchronization.services.retry import MAX_TENTATIVAS

    erro = (evento.last_error or "")[:500]
    if evento.status == EventStatus.DEAD:
        logger.error("sync: DESISTIU de %s/%s após %s tentativa(s) — %s",
                     evento.entity_type, evento.entity_id, evento.attempts, erro)
        return
    proxima = timezone.localtime(evento.next_attempt_at).strftime("%H:%M:%S") if evento.next_attempt_at else "agora"
    logger.warning("sync: FALHOU %s/%s (tentativa %s de %s, próxima às %s) — %s",
                   evento.entity_type, evento.entity_id, evento.attempts, MAX_TENTATIVAS,
                   proxima, erro)
