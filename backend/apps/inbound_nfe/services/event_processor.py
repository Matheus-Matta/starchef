"""
Processador de eventos da distribuição DF-e (resEvento e procEventoNFe).
Vincula eventos às NF-es correspondentes e dispara cancelamento e estornos
quando eventos fiscais de cancelamento (tpEvento=110111) são recebidos.
"""

import logging
from typing import Optional, List
from django.utils import timezone

from apps.inbound_nfe.models import DFeDistributionDocument, InboundNFe, NFeEvent
from apps.inbound_nfe.services.event_parser import parse_nfe_event
from apps.inbound_nfe.services.cancellation import apply_cancellation

logger = logging.getLogger(__name__)


def process_distribution_event(doc: DFeDistributionDocument) -> Optional[NFeEvent]:
    """
    Processa um documento DF-e do tipo evento (resEvento ou procEventoNFe).
    1. Executa o parser do XML.
    2. Registra ou atualiza o NFeEvent correspondente de forma idempotente.
    3. Se houver InboundNFe existente com a mesma access_key, vincula.
    4. Se for cancelamento formal homologado (110111), dispara apply_cancellation.
    5. Atualiza o status do DFeDistributionDocument para PROCESSING_OK.
    """
    try:
        parsed = parse_nfe_event(doc.xml)
    except Exception as e:
        logger.error(f"Erro ao analisar XML do evento doc NSU={doc.nsu}: {e}")
        doc.processing_status = DFeDistributionDocument.PROCESSING_ERROR
        doc.processing_error = f"Erro no parser de evento: {e}"[:2000]
        doc.processed_at = timezone.now()
        doc.save(update_fields=["processing_status", "processing_error", "processed_at"])
        return None

    if parsed.access_key and not doc.access_key:
        doc.access_key = parsed.access_key

    # Buscar InboundNFe correspondente se já existir
    invoice = InboundNFe.all_objects.filter(
        account=doc.account,
        access_key=parsed.access_key,
    ).first()

    event, created = NFeEvent.all_objects.update_or_create(
        account=doc.account,
        access_key=parsed.access_key,
        event_code=parsed.event_code,
        sequence=parsed.sequence,
        defaults={
            "restaurant": doc.restaurant,
            "branch": doc.branch,
            "nfe": invoice,
            "event_description": parsed.event_description or f"Evento {parsed.event_code}",
            "event_datetime": parsed.event_datetime or doc.received_at or timezone.now(),
            "protocol": parsed.protocol,
            "sefaz_cstat": parsed.sefaz_cstat,
            "sefaz_reason": parsed.cancellation_reason or parsed.correction_text or parsed.sefaz_reason,
            "nsu": doc.nsu,
            "schema": doc.schema,
            "xml": doc.xml,
            "processing_status": NFeEvent.PROCESSING_PROCESSED,
            "processed_at": timezone.now(),
        },
    )

    logger.info(
        f"Evento DF-e registrado (NSU={doc.nsu}, tpEvento={parsed.event_code}, "
        f"chave={parsed.access_key}, seq={parsed.sequence})"
    )

    # Se for cancelamento homologado
    if parsed.is_effective_cancellation:
        logger.warning(
            f"Evento de CANCELAMENTO (110111) identificado para chave {parsed.access_key} (NSU {doc.nsu})"
        )
        if invoice:
            apply_cancellation(
                invoice=invoice,
                event=event,
                protocol=parsed.protocol,
                reason=parsed.cancellation_reason or parsed.sefaz_reason,
                event_datetime=parsed.event_datetime,
                nsu=doc.nsu,
            )

    doc.processing_status = DFeDistributionDocument.PROCESSING_OK
    doc.processed_at = timezone.now()
    doc.save(update_fields=["access_key", "processing_status", "processed_at"])

    return event


def apply_pending_events(invoice: InboundNFe) -> List[NFeEvent]:
    """
    Associa eventos que tenham chegado antes da NF-e ser baixada/criada.
    Se algum desses eventos for de cancelamento, aplica imediatamente.
    """
    if not invoice or not invoice.access_key:
        return []

    events = NFeEvent.all_objects.filter(
        account=invoice.account,
        access_key=invoice.access_key,
    )

    applied = []
    for ev in events:
        if ev.nfe_id != invoice.id:
            ev.nfe = invoice
            ev.save(update_fields=["nfe", "updated_at"])

        if ev.is_cancellation:
            apply_cancellation(
                invoice=invoice,
                event=ev,
                protocol=ev.protocol,
                reason=ev.cancellation_reason or ev.sefaz_reason,
                event_datetime=ev.event_datetime,
                nsu=ev.nsu,
            )
        applied.append(ev)

    return applied
