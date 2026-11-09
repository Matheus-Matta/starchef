# Carrega o app do Celery junto com o Django: sem isto o processo web
# enfileirava no app PADRÃO, sem broker, e toda ação em massa sumia calada
# (ver `tests/test_celery_app_carregado.py`).
from config.celery import app as celery_app

__all__ = ("celery_app",)
