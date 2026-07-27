from .base import *  # noqa: F403

DEBUG = True
USE_SQLITE_DATABASE = True
USE_LOCAL_MEMORY_SERVICES = True
globals().update(build_database_settings(USE_SQLITE_DATABASE))  # noqa: F405
globals().update(build_runtime_service_settings(USE_LOCAL_MEMORY_SERVICES))  # noqa: F405

# Desenvolvimento: o e-mail completo e o link aparecem no terminal do Django.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
