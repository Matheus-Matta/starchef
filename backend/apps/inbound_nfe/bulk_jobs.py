"""Lotes pesados de NF-e de entrada executados fora da requisição."""
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction

from apps.bulk_jobs.models import BulkJob, BulkJobFile
from apps.bulk_jobs.services import dispatch_bulk_job, enqueue_bulk_job
from apps.inbound_nfe.models import InboundNFe

MAX_RECONCILE = 100
MAX_UPLOAD_FILES = 50
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def enqueue_reconcile(request, queryset):
    ids = request.data.get("ids") or request.data.get("nfe_ids") or []
    if ids and not isinstance(ids, list):
        raise ValidationError("Envie uma lista de notas fiscais.")
    ids = list(dict.fromkeys(str(pk) for pk in ids))
    if len(ids) > MAX_RECONCILE:
        raise ValidationError(f"Selecione no máximo {MAX_RECONCILE} notas por conciliação.")
    if ids:
        queryset = queryset.filter(pk__in=ids)
    else:
        queryset = queryset.exclude(fiscal_status=InboundNFe.FISCAL_CANCELLED).filter(
            status__in=[
                InboundNFe.STATUS_PENDING_MAPPING,
                InboundNFe.STATUS_PENDING_RECEIPT,
                InboundNFe.STATUS_SUMMARY,
            ]
        )[:20]
    visible = [str(pk) for pk in queryset.values_list("pk", flat=True)]
    return enqueue_bulk_job(
        account=request.account,
        user=request.user,
        action=BulkJob.INBOUND_RECONCILE,
        payload={"ids": visible},
        total=len(visible),
    )


def enqueue_xml_import(*, account, user, files, restaurant):
    files = list(files)
    if len(files) > MAX_UPLOAD_FILES:
        raise ValidationError(f"Envie no máximo {MAX_UPLOAD_FILES} arquivos por lote.")
    if sum(getattr(upload, "size", 0) for upload in files) > MAX_UPLOAD_BYTES:
        raise ValidationError("O lote de XML/ZIP pode ter no máximo 25 MB.")
    with transaction.atomic():
        job = enqueue_bulk_job(
            account=account,
            user=user,
            action=BulkJob.INBOUND_XML_IMPORT,
            payload={"restaurant_id": str(restaurant.pk) if restaurant else None},
            total=len(files),
            dispatch=False,
        )
        for upload in files:
            BulkJobFile.objects.create(
                account=account,
                job=job,
                file=upload,
                original_name=upload.name[:255],
            )
        dispatch_bulk_job(job)
    return job


def run_inbound_bulk_job(job):
    if job.action == BulkJob.INBOUND_RECONCILE:
        return _reconcile(job)
    return _import_xml(job)


def _reconcile(job):
    from apps.inbound_nfe.services.status_query import query_nfe_status_sefaz

    result = {"queried": 0, "cancelled": 0, "authorized": 0, "errors": 0, "results": []}
    invoices = InboundNFe.objects.filter(pk__in=job.payload["ids"])
    for invoice in invoices:
        if not invoice.access_key or len(invoice.access_key) != 44:
            continue
        try:
            status = query_nfe_status_sefaz(invoice, actor=job.requested_by)
        except Exception as exc:  # noqa: BLE001 — uma nota não interrompe as outras
            result["errors"] += 1
            result["results"].append({"id": str(invoice.pk), "error": str(exc)})
            continue
        result["queried"] += 1
        result["cancelled"] += int(bool(status.get("is_cancelled")))
        result["authorized"] += int(status.get("fiscal_status") == InboundNFe.FISCAL_AUTHORIZED)
        result["results"].append({"id": str(invoice.pk), "cstat": status.get("cstat")})
    return result


def _import_xml(job):
    from apps.inbound_nfe.services.importer import import_uploaded_files
    from apps.restaurants.models import Restaurant

    restaurant = Restaurant.objects.filter(pk=job.payload.get("restaurant_id")).first()
    records = list(job.files.all())
    files = []
    try:
        for record in records:
            record.file.open("rb")
            files.append(File(record.file, name=record.original_name))
        return import_uploaded_files(files=files, account=job.account, restaurant=restaurant)
    finally:
        for uploaded in files:
            uploaded.close()
        for record in records:
            record.file.delete(save=False)
            record.delete()
