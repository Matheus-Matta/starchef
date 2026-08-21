from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from apps.accounts.signals import sync_permission_catalog

        post_migrate.connect(
            sync_permission_catalog,
            sender=self,
            dispatch_uid="accounts.sync_permission_catalog",
        )

