"""O zeramento sai da requisição e termina no worker com aviso pelo sino."""
import uuid
from decimal import Decimal
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.bulk_jobs.models import BulkJob
from apps.bulk_jobs.services import _dispatch, run_bulk_job
from apps.bulk_jobs.tasks import recover_bulk_jobs
from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.notifications.models import Notification
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db
URL = "/api/v1/commands/bulk-reset/"


def test_entrega_o_lote_ao_worker_sem_prender_a_requisicao(
    api_client,
    account,
    restaurant,
    branch,
    manager_user,
    django_capture_on_commit_callbacks,
):
    """O operador recebe o aceite; o worker faz o zeramento depois."""
    with tenant_context(account):
        category = ProductCategory.objects.create(account=account, restaurant=restaurant, name="Lanches")
        product = Product.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            category=category,
            name="X-Burger",
            internal_code=f"BULK{uuid.uuid4().hex[:6]}",
            sale_price=Decimal("25.00"),
        )
        command = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=10)
        launch_item(command=command, product=product, user=manager_user, quantity=1)

    with mock.patch("apps.bulk_jobs.tasks.run_bulk_job_task.delay") as enqueue:
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(
                URL,
                {"ids": [str(command.pk)], "reason": "Fim do expediente"},
                format="json",
            )

    assert response.status_code == 202, response.content
    assert response.data["status"] == BulkJob.QUEUED
    enqueue.assert_called_once_with(response.data["id"])
    with tenant_context(account):
        assert not CommandItem.objects.filter(command=command, status=CommandItem.STATUS_CANCELLED).exists()

    job = run_bulk_job(response.data["id"])

    assert job.status == BulkJob.DONE
    assert job.payload == {}
    assert job.result["reset"][0]["number"] == 10
    notice = Notification.all_objects.get(recipient=manager_user, entity="bulk_jobs.BulkJob")
    assert "1 comanda(s) zerada(s)" in notice.body
    assert run_bulk_job(job.pk) is None


def test_fila_indisponivel_mantem_job_para_o_agendador(account, manager_user):
    job = BulkJob.objects.create(
        account=account,
        requested_by=manager_user,
        action=BulkJob.COMMAND_RESET,
        payload={},
        total=1,
    )
    task = mock.Mock()
    task.delay.side_effect = ConnectionError("Redis fora")

    _dispatch(task, job.pk)

    job.refresh_from_db()
    assert job.status == BulkJob.QUEUED


def test_agendador_reentrega_job_que_ficou_na_fila(account, manager_user):
    job = BulkJob.objects.create(
        account=account,
        requested_by=manager_user,
        action=BulkJob.COMMAND_RESET,
        payload={},
        total=1,
    )
    BulkJob.all_objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(minutes=2))

    with mock.patch("apps.bulk_jobs.tasks.run_bulk_job_task.delay") as enqueue:
        recover_bulk_jobs()

    enqueue.assert_called_once_with(str(job.pk))
