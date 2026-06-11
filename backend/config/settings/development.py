from .base import *  # noqa: F403

DEBUG = True
USE_SQLITE_DATABASE = True
USE_LOCAL_MEMORY_SERVICES = True
globals().update(build_database_settings(USE_SQLITE_DATABASE))  # noqa: F405
globals().update(build_runtime_service_settings(USE_LOCAL_MEMORY_SERVICES))  # noqa: F405
