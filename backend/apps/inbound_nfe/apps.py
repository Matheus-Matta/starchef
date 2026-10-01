from django.apps import AppConfig


class InboundNfeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inbound_nfe"
    verbose_name = "Entrada de NF-e"

    def ready(self):
        from apps.inbound_nfe import signals  # noqa: F401
