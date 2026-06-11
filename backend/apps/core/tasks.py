from contextlib import contextmanager

from apps.accounts.models import Account
from apps.core.tenant import tenant_context


@contextmanager
def celery_tenant_context(account_id):
    account = Account.objects.get(pk=account_id, is_active=True)
    with tenant_context(account):
        yield account
