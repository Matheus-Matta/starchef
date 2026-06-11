from contextlib import contextmanager
from contextvars import ContextVar

_current_account = ContextVar("current_account", default=None)


def set_current_account(account):
    return _current_account.set(account)


def get_current_account():
    return _current_account.get()


def clear_current_account():
    _current_account.set(None)


@contextmanager
def tenant_context(account):
    token = set_current_account(account)
    try:
        yield
    finally:
        _current_account.reset(token)

