"""A conta corrente da requisição — e, quando RLS está ligada, da conexão.

O `ContextVar` sozinho diz ao PYTHON qual é a conta. Isso basta enquanto o
isolamento depender do `TenantQuerySetMixin`, mas não basta para uma política
do PostgreSQL: o banco precisa ouvir a mesma resposta. Por isso toda troca de
conta aqui passa por `rls.aplicar_conta` — que não faz nada enquanto RLS
estiver desligada, e é assim que este módulo continua servindo os dois modos
sem ter dois caminhos.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_current_account = ContextVar("current_account", default=None)


def set_current_account(account):
    token = _current_account.set(account)
    _sincronizar_banco(account)
    return token


def get_current_account():
    return _current_account.get()


def clear_current_account():
    _current_account.set(None)
    _sincronizar_banco(None)


def _sincronizar_banco(account):
    """Empurra a conta para a sessão do PostgreSQL. Silenciosa sem RLS.

    Falhar aqui NÃO pode derrubar a requisição: se a conexão caiu, o erro
    verdadeiro vem da consulta seguinte, com mensagem que diz o que houve. Um
    estouro neste ponto trocaria "banco indisponível" por um traceback sobre
    `set_config`, e mandaria quem for diagnosticar para o lugar errado.
    """
    from apps.core import rls

    try:
        rls.aplicar_conta(account)
    except Exception:  # noqa: BLE001 — ver docstring
        import logging

        logging.getLogger(__name__).warning(
            "rls: não foi possível fixar a conta na sessão do banco", exc_info=True
        )


@contextmanager
def tenant_context(account):
    token = set_current_account(account)
    try:
        yield
    finally:
        anterior = _current_account.get()
        _current_account.reset(token)
        # Restaura no BANCO o que o `reset` restaurou no Python. Sem esta
        # linha, sair de um bloco aninhado deixaria a sessão do PostgreSQL
        # falando pela conta de dentro enquanto o Python já voltou para a de
        # fora — e as duas discordando é pior que qualquer uma das duas
        # sozinha.
        if _current_account.get() is not anterior:
            _sincronizar_banco(_current_account.get())
