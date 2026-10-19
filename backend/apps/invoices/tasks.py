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


@shared_task(name="invoices.emitir_nota_do_pedido_pago")
def emitir_nota_do_pedido_pago_task(order_id, user_id=None, auto_print=True):
    """A NFC-e do pedido que acabou de ser pago, fora da requisição do caixa.

    Ver `apps.invoices.signals`. Falhar aqui não deixa venda sem nota: o PDV
    pede a nota logo depois (`/invoices/emit/`), e a loja varre os pagos sem
    nota (`emitir_pagos_sem_nota`).
    """
    from django.contrib.auth import get_user_model

    from apps.invoices.services import issue_invoice_for_paid_order
    from apps.orders.models import Order

    pedido = Order.all_objects.select_related("account", "restaurant", "branch").filter(pk=order_id).first()
    if pedido is None:
        return False
    usuario = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    return issue_invoice_for_paid_order(pedido, user=usuario, auto_print=auto_print) is not None
