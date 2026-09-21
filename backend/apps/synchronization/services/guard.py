"""O portão de ambiente: em qual mundo esta instalação está falando.

Este módulo é chamado em todo caminho de entrada (worker, consumer, botão do
Admin, provisionamento). O objetivo é que nenhum deles dependa de alguém ter
lembrado de conferir: quem esquece, recebe a exceção.

O que ele recusa é um valor DESCONHECIDO. `SYNC_ENVIRONMENT=prod` (em vez de
`production`) ou `SYNC_ENVIRONMENT=` vazio não podem passar como "um ambiente
qualquer": passariam, e aí nenhum nó encontraria nenhum outro, com a mensagem
de erro falando de credencial em vez de configuração.

Estar em ambientes DIFERENTES é outra coisa, e quem confere isso é
`authentication._validar_ambiente`: ali o nó precisa declarar o mesmo ambiente
que esta instalação. Enquanto só existia `development`, as duas checagens eram
a mesma por acidente — e separá-las foi o que permitiu abrir `production` sem
perder a proteção.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.synchronization.constants import ENVIRONMENTS_ALLOWED

MENSAGEM = (
    "SYNC_ENVIRONMENT precisa ser um destes: "
    + ", ".join(sorted(ENVIRONMENTS_ALLOWED))
    + ". Ajuste a variável ou mantenha SYNC_ENABLED=false."
)


class SyncDisabled(ImproperlyConfigured):
    """Sincronização desligada ou em ambiente não liberado."""


def current_environment():
    return str(getattr(settings, "SYNC_ENVIRONMENT", "") or "").strip().lower()


def is_enabled():
    return bool(getattr(settings, "SYNC_ENABLED", False))


def environment_is_allowed(environment=None):
    """O valor é um ambiente que existe? Não diz nada sobre ser o NOSSO."""
    return (environment or current_environment()) in ENVIRONMENTS_ALLOWED


def is_production(environment=None):
    from apps.synchronization.constants import ENVIRONMENT_PRODUCTION

    return (environment or current_environment()) == ENVIRONMENT_PRODUCTION


def matches_environment(environment):
    """O nó do outro lado está no MESMO mundo que esta instalação?

    Separado de `environment_is_allowed` de propósito. Um vale `production`
    como ambiente existente; o outro recusa uma loja de homologação tentando
    entrar na nuvem de produção, que é um cenário completamente diferente e
    merece recusa mesmo com credencial perfeita.
    """
    valor = str(environment or "").strip().lower()
    return bool(valor) and valor == current_environment()


def ensure_environment(environment=None):
    """Recusa ambiente desconhecido. Não tem exceção."""
    valor = environment or current_environment()
    if valor not in ENVIRONMENTS_ALLOWED:
        raise SyncDisabled(f"{MENSAGEM} (recebido: {valor or 'vazio'})")
    return valor


def ensure_enabled():
    """Recusa quando a sincronização está desligada OU fora de development."""
    if not is_enabled():
        raise SyncDisabled("SYNC_ENABLED=false: a sincronização não está ligada nesta instalação.")
    return ensure_environment()


def node_type():
    return str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().upper()
