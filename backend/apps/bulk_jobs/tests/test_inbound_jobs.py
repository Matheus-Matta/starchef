"""SEFAZ e arquivos XML não podem manter a requisição presa."""
from unittest import mock

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.bulk_jobs.models import BulkJob, BulkJobFile
from apps.bulk_jobs.services import run_bulk_job
from apps.core.tenant import tenant_context
from apps.inbound_nfe.models import InboundNFe

pytestmark = pytest.mark.django_db


def _invoice(account, restaurant, branch):
    with tenant_context(account):
        return InboundNFe.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            access_key="1" * 44,
            number="123",
            status=InboundNFe.STATUS_PENDING_RECEIPT,
        )


def test_conciliacao_sefaz_responde_antes_de_consultar(
    api_client,
    account,
    restaurant,
    branch,
    django_capture_on_commit_callbacks,
):
    invoice = _invoice(account, restaurant, branch)
    with mock.patch("apps.bulk_jobs.tasks.run_bulk_job_task.delay") as enqueue:
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(
                "/api/v1/inbound-nfe/reconcile-status/",
                {"nfe_ids": [str(invoice.pk)]},
                format="json",
            )

    assert response.status_code == 202
    enqueue.assert_called_once_with(response.data["id"])
    with mock.patch(
        "apps.inbound_nfe.services.status_query.query_nfe_status_sefaz",
        return_value={"fiscal_status": InboundNFe.FISCAL_AUTHORIZED, "cstat": "100"},
    ) as query:
        job = run_bulk_job(response.data["id"])
    assert job.result["queried"] == 1
    assert job.result["authorized"] == 1
    query.assert_called_once()


def test_upload_guarda_arquivo_so_ate_o_worker(
    api_client,
    account,
    restaurant,
    settings,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    settings.MEDIA_ROOT = tmp_path
    upload = SimpleUploadedFile("nota.xml", b"<NFe />", content_type="application/xml")
    with mock.patch("apps.bulk_jobs.tasks.run_bulk_job_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(
                "/api/v1/inbound-nfe/upload-xml/",
                {"files": [upload], "restaurant": str(restaurant.pk)},
                format="multipart",
            )

    assert response.status_code == 202
    job = BulkJob.all_objects.get(pk=response.data["id"])
    record = BulkJobFile.all_objects.get(job=job)
    stored_name = record.file.name
    assert default_storage.exists(stored_name)
    summary = {"total_processed": 1, "total_errors": 0, "results": [], "errors": []}
    with mock.patch("apps.inbound_nfe.services.importer.import_uploaded_files", return_value=summary):
        job = run_bulk_job(job.pk)

    assert job.status == BulkJob.DONE
    assert job.result["total_processed"] == 1
    assert not default_storage.exists(stored_name)
