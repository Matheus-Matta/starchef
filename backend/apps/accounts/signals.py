"""Sinais de inicialização do catálogo global de permissões."""

from django.conf import settings

from apps.accounts.management.commands.sync_permissions import sync_permissions
from apps.accounts.models import CosmosConfig, FocusNfeConfig


def sync_permission_catalog(**_kwargs):
    """Mantém o catálogo disponível depois de toda execução de ``migrate``.

    O deploy de produção executa migrations ao iniciar o backend. Usar o sinal
    ``post_migrate`` garante que bancos novos e bancos já existentes recebam o
    catálogo sem depender de um comando operacional separado.
    """

    sync_permissions()


def focus_nfe_defaults_from_settings():
    """Valores do .env usados somente para provisionar uma nova conta."""

    return {
        "master_token": getattr(settings, "FOCUS_NFE_MASTER_TOKEN", ""),
        "production_url": getattr(settings, "FOCUS_NFE_PRODUCTION_URL", ""),
        "homologation_url": getattr(settings, "FOCUS_NFE_HOMOLOGATION_URL", ""),
        "timeout_seconds": getattr(settings, "FOCUS_NFE_TIMEOUT_SECONDS", 30),
        "auto_sync": getattr(settings, "FOCUS_NFE_AUTO_SYNC", True),
        "company_dry_run": getattr(settings, "FOCUS_NFE_COMPANY_DRY_RUN", False),
        "webhook_url": getattr(settings, "FOCUS_NFE_WEBHOOK_URL", ""),
        "webhook_authorization": getattr(settings, "FOCUS_NFE_WEBHOOK_AUTHORIZATION", ""),
        "webhook_authorization_header": getattr(
            settings,
            "FOCUS_NFE_WEBHOOK_AUTHORIZATION_HEADER",
            "Authorization",
        ),
    }


def provision_account_focus_nfe_config(sender, instance, created, **_kwargs):
    """Toda conta nasce com sua configuracao Focus, ainda que vazia."""

    if created:
        FocusNfeConfig.objects.get_or_create(
            account=instance,
            defaults=focus_nfe_defaults_from_settings(),
        )


def provision_account_cosmos_config(sender, instance, created, **_kwargs):
    """Toda conta nasce com a integracao Cosmos opcional e desativada."""

    if created:
        CosmosConfig.objects.get_or_create(account=instance)


def provision_account_system_roles(sender, instance, created, **_kwargs):
    """Toda conta nasce com os 4 Perfis de Acesso fixos (ver role_catalog)."""

    if created:
        from apps.accounts.role_catalog import ensure_system_roles

        ensure_system_roles(instance)
