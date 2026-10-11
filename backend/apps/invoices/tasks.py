from celery import shared_task
from django.db import transaction

from apps.invoices.focus import FocusCompanySyncResult, FocusNfeApiError, FocusNfeConfigurationError, sync_focus_company
from apps.invoices.models import FiscalConfig


@shared_task(
    bind=True,
    name="invoices.sync_focus_company",
    max_retries=5,
)
def sync_focus_company_task(self, config_id):
    retry_error = None
    result = None
    with transaction.atomic():
        config = (
            FiscalConfig.all_objects.select_related("account", "restaurant", "branch")
            .select_for_update(of=("self",))
            .filter(pk=config_id, deleted_at__isnull=True)
            .first()
        )
        if config is None or config.provider != FiscalConfig.PROVIDER_FOCUS_NFE:
            return False
        try:
            result = sync_focus_company(config)
        except FocusNfeConfigurationError:
            return False
        except FocusNfeApiError as exc:
            if not exc.retryable:
                return False
            # Agenda o retry somente depois de sair do bloco atomico. Assim o
            # status/erro salvo pelo servico nao e desfeito pelo Retry do Celery.
            retry_error = exc
    if retry_error is not None:
        countdown = min(60, 2 ** (self.request.retries + 1))
        raise self.retry(exc=retry_error, countdown=countdown)
    return not isinstance(result, FocusCompanySyncResult) or result.synced


@shared_task(name="invoices.reprocess_pending")
def reprocess_pending_task():
    """Retransmite as notas pendentes (contingência, espera, conciliação).

    Existia só como comando manual: a nota em contingência ficaria pendente
    até alguém lembrar de rodar. A NFC-e em contingência tem 24 h para chegar
    à SEFAZ (docs/FISCAL_ACBRLIB.md).
    """
    from apps.invoices.services import reprocess_pending_fiscal_invoices

    return reprocess_pending_fiscal_invoices()


@shared_task(name="invoices.emitir_pagos_sem_nota")
def emitir_pagos_sem_nota_task():
    """Na loja com ACBrLib: emite a nota da venda paga que chegou sem nota."""
    from apps.invoices.emissao_da_loja import emitir_pagos_sem_nota

    return emitir_pagos_sem_nota()
