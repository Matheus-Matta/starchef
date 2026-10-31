"""Cancelar e excluir pedidos em massa também rodam fora da requisição."""
from unittest import mock

import pytest

from apps.bulk_jobs.models import BulkJob
from apps.bulk_jobs.services import run_bulk_job
from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db


def _order(account, restaurant, branch, user):
    with tenant_context(account):
        return create_order(
            restaurant=restaurant,
            branch=branch,
            order_type=Order.TYPE_COUNTER,
            user=user,
        )


def test_cancelamento_em_massa_fica_no_worker(api_client, account, restaurant, branch, manager_user):
    order = _order(account, restaurant, branch, manager_user)

    with mock.patch("apps.bulk_jobs.tasks.run_bulk_job_task.delay"):
        response = api_client.post(
            "/api/v1/orders/bulk-cancel/",
            {"ids": [str(order.pk)], "reason": "Teste"},
            format="json",
        )

    assert response.status_code == 202
    order.refresh_from_db()
    assert order.status == Order.STATUS_OPEN
    job = run_bulk_job(response.data["id"])
    order.refresh_from_db()
    assert job.status == BulkJob.DONE
    assert job.result["cancelled"] == 1
    assert order.status == Order.STATUS_CANCELLED


def test_exclusao_em_massa_fica_no_worker(api_client, account, restaurant, branch, manager_user):
    order = _order(account, restaurant, branch, manager_user)

    with mock.patch("apps.bulk_jobs.tasks.run_bulk_job_task.delay"):
        response = api_client.post(
            "/api/v1/orders/bulk-delete/",
            {"ids": [str(order.pk)]},
            format="json",
        )

    assert response.status_code == 202
    assert Order.all_objects.get(pk=order.pk).deleted_at is None
    job = run_bulk_job(response.data["id"])
    assert job.status == BulkJob.DONE
    assert job.result["deleted"] == 1
    assert Order.all_objects.get(pk=order.pk).deleted_at is not None
