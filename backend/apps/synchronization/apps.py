from django.apps import AppConfig


class SynchronizationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.synchronization"
    verbose_name = "Sincronização"

    def ready(self):
        # O catálogo precisa ser importado para popular o registro; os signals,
        # para capturar as gravações. Nenhum dos dois toca no banco aqui.
        from apps.synchronization import catalog, checks, signals  # noqa: F401
