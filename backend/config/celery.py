from celery import Celery

from config.env import configure_django_settings

configure_django_settings()

app = Celery("starchef")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
