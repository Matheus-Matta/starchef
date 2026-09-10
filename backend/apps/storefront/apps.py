from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.storefront"
    verbose_name = "Cardápio digital (storefront)"

    def ready(self):
        from apps.storefront import signals  # noqa: F401  (conecta a invalidação de cache)
