"""O relógio da loja comparado com o da nuvem.

A regra do clone é "vence a versão mais nova", e a versão é o `updated_at` de
quem gravou. Um computador da loja com o relógio 3 minutos atrasado faz TODA
edição da loja perder para a da nuvem feita até 3 minutos antes — e ninguém
vê erro nenhum, o dado só "volta" sozinho.

A medida é feita no aperto de mão: o `sent_at` da nuvem contra o relógio
daqui. Inclui o tempo de rede (milissegundos), então só um desvio acima de
[LIMITE] vira alerta.
"""
import logging
from datetime import datetime, timezone as dt_timezone

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

LIMITE_SEGUNDOS = 2.0
CHAVE_DO_CACHE = "sync:desvio_do_relogio"


def desvio_em_segundos(sent_at, agora=None):
    """Quanto o relógio daqui está À FRENTE da nuvem (negativo = atrasado)."""
    if not sent_at:
        return None
    try:
        enviado = datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(enviado):
        enviado = enviado.replace(tzinfo=dt_timezone.utc)
    return ((agora or timezone.now()) - enviado).total_seconds()


def registrar_desvio(sent_at):
    """Mede, guarda para o Admin e avisa no log quando passa do limite."""
    desvio = desvio_em_segundos(sent_at)
    if desvio is None:
        return None
    try:
        cache.set(CHAVE_DO_CACHE, round(desvio, 1), timeout=None)
    except Exception:  # noqa: BLE001 — medir o relógio nunca derruba a conexão
        pass
    if abs(desvio) > LIMITE_SEGUNDOS:
        logger.error(
            "sync: o relógio desta loja está %.1f s %s da nuvem. Com a regra do "
            "mais novo, isso decide quem vence: acerte a hora do servidor (NTP).",
            abs(desvio), "à frente" if desvio > 0 else "atrás",
        )
    return desvio


def desvio_conhecido():
    try:
        return cache.get(CHAVE_DO_CACHE)
    except Exception:  # noqa: BLE001
        return None
