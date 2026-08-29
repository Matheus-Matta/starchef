from django.apps import AppConfig
from django.db.models.signals import post_migrate, post_save


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from apps.accounts.models import Account
        from apps.accounts.signals import (
            provision_account_focus_nfe_config,
            provision_account_system_roles,
            sync_permission_catalog,
        )

        post_migrate.connect(
            sync_permission_catalog,
            sender=self,
            dispatch_uid="accounts.sync_permission_catalog",
        )
        post_save.connect(
            provision_account_focus_nfe_config,
            sender=Account,
            dispatch_uid="accounts.provision_focus_nfe_config",
        )
        post_save.connect(
            provision_account_system_roles,
            sender=Account,
            dispatch_uid="accounts.provision_system_roles",
        )

