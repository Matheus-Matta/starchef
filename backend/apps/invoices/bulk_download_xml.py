"""Download em massa de XMLs de notas fiscais (ZIP)."""
import io
import logging
import zipfile
from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.db.models import Q, QuerySet

from apps.bulk_jobs.models import BulkJob
from apps.bulk_jobs.services import enqueue_bulk_job, queued_response
from apps.invoices.models import Invoice


class BulkDownloadXmlSerializer:
    """Valida os parametros de filtro para download em massa."""

    def __init__(self, data):
        self.data = data
        self.errors = {}

    def is_valid(self):
        """Valida os dados e retorna True se valido."""
        # Data inicio/fim sao opcionais mas devem ser strings de data
        date_from = self.data.get("date_from")
        date_to = self.data.get("date_to")

        if date_from:
            try:
                datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                self.errors["date_from"] = "Data invalida (use ISO 8601: YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS)"

        if date_to:
            try:
                datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                self.errors["date_to"] = "Data invalida (use ISO 8601: YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS)"

        # Status deve ser um dos valores validos
        status = self.data.get("status")
        valid_statuses = [Invoice.STATUS_ISSUED, Invoice.STATUS_PENDING, Invoice.STATUS_ERROR]
        if status and status not in valid_statuses:
            self.errors["status"] = f"Status invalido: {status}"

        # Modelo deve ser um dos valores validos
        model = self.data.get("document_model")
        valid_models = [Invoice.MODEL_NFCE, Invoice.MODEL_NFE]
        if model and model not in valid_models:
            self.errors["document_model"] = f"Modelo invalido: {model}"

        return not bool(self.errors)

    def validated_data(self):
        """Retorna os dados validados."""
        return self.data


def build_download_filters(
    account_id,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    document_model: Optional[str] = None,
    restaurant_id: Optional[str] = None,
) -> QuerySet:
    """Monta a QuerySet com os filtros para download de XMLs."""
    queryset = Invoice.objects.filter(
        account_id=account_id,
        xml_content__isnull=False,
    ).exclude(xml_content="")

    # Filtro de data (criacao)
    if date_from:
        queryset = queryset.filter(created_at__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__lte=date_to)

    # Filtro de status: por padrao, so autorizada
    if status:
        queryset = queryset.filter(status=status)
    else:
        queryset = queryset.filter(status=Invoice.STATUS_ISSUED)

    # Filtro de modelo
    if document_model:
        queryset = queryset.filter(document_model=document_model)

    # Filtro de restaurante
    if restaurant_id:
        queryset = queryset.filter(restaurant_id=restaurant_id)

    return queryset.select_related("restaurant", "order").order_by("-created_at")


def generate_xml_zip(invoices) -> bytes:
    """Gera um ZIP com todos os XMLs das notas.

    Nomeia cada arquivo como: {access_key}.xml
    Agrupa em pastas por restaurante se houver multiplos.
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for invoice in invoices:
            if not invoice.xml_content or not invoice.access_key:
                continue

            # Nome do arquivo: CHAVE_ACESSO.xml
            filename = f"{invoice.access_key}.xml"

            # Se houver restaurante, coloca em subpasta
            if invoice.restaurant:
                filename = f"{invoice.restaurant.slug}/{filename}"

            # Evita duplicatas (nao deve acontecer, mas por seguranca)
            try:
                zip_file.writestr(filename, invoice.xml_content)
            except (OSError, ValueError):
                # Se duplicata, ignora
                pass

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def run_bulk_download_xml_job(job: BulkJob) -> dict:
    """Executa o job de download em massa de XMLs.

    Gera um ZIP e o armazena para download. O usuario e notificado quando
    pronto.
    """
    from apps.core.storage import storage_service

    logger = logging.getLogger(__name__)
    payload = job.payload

    try:
        # Monta a QuerySet com os filtros
        queryset = build_download_filters(
            account_id=job.account_id,
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            status=payload.get("status"),
            document_model=payload.get("document_model"),
            restaurant_id=payload.get("restaurant_id"),
        )

        count = queryset.count()
        if count == 0:
            return {
                "status": "empty",
                "message": "Nenhum XML encontrado com os filtros especificados.",
                "total": 0,
            }

        # Gera o ZIP
        zip_data = generate_xml_zip(queryset)
        zip_size = len(zip_data)

        # Armazena o ZIP (com nome incluindo data/hora)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"notas_fiscais_{timestamp}.zip"
        zip_path = f"xmls/{zip_filename}"

        # Salva no storage (S3 ou disco)
        url = storage_service().upload_file(zip_data, zip_path)

        logger.info(
            "Download em massa de XMLs concluido: %d notas, %s bytes",
            count, zip_size
        )

        result = {
            "status": "completed",
            "message": f"{count} XMLs gerados em {zip_filename}",
            "total": count,
            "zip_filename": zip_filename,
            "zip_size_mb": round(Decimal(zip_size) / (1024 ** 2), 2),
            "download_url": url,
        }

        # Notifica o usuario que o download esta pronto
        _send_download_ready_notification(job, result)

        return result

    except Exception as exc:
        logger.exception("Erro ao gerar download em massa de XMLs")
        return {
            "status": "failed",
            "message": f"Erro ao gerar ZIP: {str(exc)}",
            "error": str(exc),
        }


def _send_download_ready_notification(job: BulkJob, result: dict):
    """Envia notificacao ao usuario que o download esta pronto."""
    try:
        from apps.notifications.services import notify
        from apps.notifications.models import Notification

        notify(
            [job.requested_by],
            account=job.account,
            level=Notification.LEVEL_SUCCESS,
            title="Download de XMLs pronto",
            body=f"{result['total']} XMLs foram gerados com sucesso.",
            url=result.get("download_url", "/notas-fiscais"),
            category=Notification.CATEGORY_SYSTEM,
            entity="invoices.Invoice",
            metadata={
                "action": "download_xml",
                "filename": result.get("zip_filename"),
                "total": result['total'],
            },
        )
    except Exception as exc:
        logger = logging.getLogger(__name__)
        logger.warning("Nao foi possivel enviar notificacao de download: %s", exc)
