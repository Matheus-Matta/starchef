from celery import shared_task

from apps.imports.services import run_import


@shared_task(name="imports.run_import")
def run_import_task(job_id):
    run_import(job_id)
