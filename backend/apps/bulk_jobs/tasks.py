from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.bulk_jobs.models import BulkJob
from apps.bulk_jobs.services import run_bulk_job


@shared_task(name="bulk_jobs.run", bind=True, acks_late=True, reject_on_worker_lost=True)
def run_bulk_job_task(self, job_id):
    run_bulk_job(job_id, task_id=self.request.id)


@shared_task(name="bulk_jobs.recover")
def recover_bulk_jobs():
    """Reentrega filas perdidas e jobs cujo worker excedeu o limite global."""
    now = timezone.now()
    stale = BulkJob.all_objects.filter(
        status=BulkJob.RUNNING,
        updated_at__lt=now - timedelta(minutes=35),
    )
    stale.update(status=BulkJob.QUEUED, worker_task_id="")
    ids = BulkJob.all_objects.filter(
        status=BulkJob.QUEUED,
        created_at__lt=now - timedelta(seconds=30),
    ).values_list("pk", flat=True)
    for job_id in ids.iterator():
        run_bulk_job_task.delay(str(job_id))
