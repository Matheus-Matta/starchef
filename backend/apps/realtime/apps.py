from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.realtime"

    def ready(self):
        from . import signals  # noqa: F401
        from .envio_em_lote import ligar_no_celery

        ligar_no_celery()

