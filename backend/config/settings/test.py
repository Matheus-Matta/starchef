from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-secret-key-for-starchef-with-enough-length"
USE_SQLITE_DATABASE = True
USE_LOCAL_MEMORY_SERVICES = True
globals().update(build_database_settings(USE_SQLITE_DATABASE))  # noqa: F405
globals().update(build_runtime_service_settings(USE_LOCAL_MEMORY_SERVICES))  # noqa: F405
DATABASES["default"]["NAME"] = BASE_DIR / "test.sqlite3"  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
