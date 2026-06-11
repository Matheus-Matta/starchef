import os
from pathlib import Path


TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}


def configure_django_settings():
    if os.getenv("DJANGO_SETTINGS_MODULE"):
        os.environ.pop("STARCHEF_SETTINGS_AUTO", None)
        return os.environ["DJANGO_SETTINGS_MODULE"]

    env_values = read_env_files()
    debug_value = os.getenv("DJANGO_DEBUG", env_values.get("DJANGO_DEBUG"))
    env_name = os.getenv("DJANGO_ENV", env_values.get("DJANGO_ENV", "")).lower()

    if parse_bool(debug_value, default=env_name not in {"production", "prod"}):
        settings_module = "config.settings.development"
    else:
        settings_module = "config.settings.production"

    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module
    os.environ["STARCHEF_SETTINGS_AUTO"] = "1"
    return settings_module


def read_env_files():
    backend_dir = Path(__file__).resolve().parents[1]
    project_dir = backend_dir.parent
    values = {}

    for env_file in (project_dir / ".env", backend_dir / ".env"):
        if not env_file.exists():
            continue
        values.update(parse_env_file(env_file))

    return values


def parse_env_file(path):
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def parse_bool(value, default=False):
    if value is None:
        return default

    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default
