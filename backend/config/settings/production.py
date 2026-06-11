from .base import *  # noqa: F403

DEBUG = False
USE_SQLITE_DATABASE = False
USE_LOCAL_MEMORY_SERVICES = False
globals().update(build_database_settings(USE_SQLITE_DATABASE))  # noqa: F405
globals().update(build_runtime_service_settings(USE_LOCAL_MEMORY_SERVICES))  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
