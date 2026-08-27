from celery import shared_task
from django.db import transaction

from apps.invoices.focus import FocusNfeApiError, FocusNfeConfigurationError, sync_focus_company
from apps.invoices.models import FiscalConfig


@shared_task(
    bind=True,
    name="invoices.sync_focus_company",
    autoretry_for=(FocusNfeApiError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def sync_focus_company_task(self, config_id):
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
            sync_focus_company(config)
        except FocusNfeConfigurationError:
            return False
    return True
