from celery import shared_task

from apps.orders.services import dispatch_due_kitchen_batches


@shared_task(name="orders.dispatch_due_kitchen_batches")
def dispatch_due_kitchen_batches_task():
    return dispatch_due_kitchen_batches()
