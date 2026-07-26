from .base import *  # noqa: F403
from decouple import config
from django.core.exceptions import ImproperlyConfigured

DEBUG = False
USE_SQLITE_DATABASE = False
USE_LOCAL_MEMORY_SERVICES = False
globals().update(build_database_settings(USE_SQLITE_DATABASE))  # noqa: F405
globals().update(build_runtime_service_settings(USE_LOCAL_MEMORY_SERVICES))  # noqa: F405

if SECRET_KEY == "unsafe-dev-key":  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY deve ser definido em produção.")
if DATABASES["default"].get("PASSWORD") in {"", "starchef"}:  # noqa: F405
    raise ImproperlyConfigured("POSTGRES_PASSWORD deve ser definido com um valor seguro em produção.")

# WhiteNoise serve os estáticos coletados (admin/DRF) direto do app, logo após o
# SecurityMiddleware — assim o /static/ funciona mesmo sem o nginx no caminho.
MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,  # noqa: F405
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("DJANGO_SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ── Sentry (monitoramento de erros/performance) ──────────────────────────────
# Opcional: só ativa se SENTRY_DSN estiver definido. Sem DSN, não há overhead.
SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            LoggingIntegration(level=None, event_level="ERROR"),
        ],
        environment=config("SENTRY_ENVIRONMENT", default="production"),
        release=config("SENTRY_RELEASE", default=None),
        # Amostragem configurável: em produção 0.1 (10%) equilibra custo x visibilidade.
        traces_sample_rate=config("SENTRY_TRACES_SAMPLE_RATE", default=0.1, cast=float),
        # Não enviar PII (corpo de requisição/headers) por padrão — dados de tenant.
        send_default_pii=config("SENTRY_SEND_PII", default=False, cast=bool),
    )
