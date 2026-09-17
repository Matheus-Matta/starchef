"""O bloqueio preventivo: nesta fase, só DEVELOPMENT roda.

Este módulo é chamado em todo caminho de entrada (worker, consumer, botão do
Admin, provisionamento). O objetivo é que nenhum deles dependa de alguém ter
lembrado de conferir: quem esquece, recebe a exceção.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.synchronization.constants import ENVIRONMENT_DEVELOPMENT

MENSAGEM = (
    "A sincronização está liberada somente em DEVELOPMENT. "
    "Ajuste SYNC_ENVIRONMENT=development ou mantenha SYNC_ENABLED=false."
)


class SyncDisabled(ImproperlyConfigured):
    """Sincronização desligada ou em ambiente não liberado."""


def current_environment():
    return str(getattr(settings, "SYNC_ENVIRONMENT", "") or "").strip().lower()


def is_enabled():
    return bool(getattr(settings, "SYNC_ENABLED", False))


def environment_is_allowed(environment=None):
    return (environment or current_environment()) == ENVIRONMENT_DEVELOPMENT


def ensure_environment(environment=None):
    """Recusa qualquer ambiente que não seja development. Não tem exceção."""
    valor = environment or current_environment()
    if valor != ENVIRONMENT_DEVELOPMENT:
        raise SyncDisabled(f"{MENSAGEM} (recebido: {valor or 'vazio'})")
    return valor


def ensure_enabled():
    """Recusa quando a sincronização está desligada OU fora de development."""
    if not is_enabled():
        raise SyncDisabled("SYNC_ENABLED=false: a sincronização não está ligada nesta instalação.")
    return ensure_environment()


def node_type():
    return str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().upper()
