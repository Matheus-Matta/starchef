import logging
from apps.notifications.models import Notification
from apps.notifications.services import notify, managers_of_account

logger = logging.getLogger(__name__)


def notify_new_inbound_nfe(invoice):
    """Notifica os administradores e gerentes da conta sobre uma nova NF-e identificada."""
    try:
        if not invoice or not invoice.account_id:
            return

        recipients = managers_of_account(invoice.account_id)
        if not recipients.exists():
            return

        number_label = f"NF-e nº {invoice.number}" if invoice.number else "Nova NF-e de compra"
        supplier = invoice.supplier_name or invoice.supplier_cnpj or "Fornecedor"
        
        try:
            val = float(invoice.total_invoice) if invoice.total_invoice else 0.0
            val_str = f" no valor de R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if val > 0 else ""
        except Exception:
            val_str = ""

        if invoice.status == "summary":
            status_desc = "Resumo identificado na SEFAZ. Aguardando download do XML completo."
        elif invoice.status == "pending_mapping":
            status_desc = "Identificada com itens pendentes de vínculo ao estoque."
        elif invoice.status == "pending_receipt":
            status_desc = "Itens vinculados automaticamente, pronta para conferência e entrada."
        elif invoice.status == "received":
            status_desc = "Entrada no estoque concluída com sucesso."
        else:
            status_desc = "Identificada no sistema."

        notify(
            recipients=recipients,
            account=invoice.account,
            category=Notification.CATEGORY_STOCK,
            level=Notification.LEVEL_INFO,
            title=f"Nova {number_label}",
            body=f"{supplier}{val_str}. {status_desc}",
            url="/inbound-nfe/",
            entity="inbound_nfe",
            object_id=str(invoice.id),
            metadata={
                "access_key": invoice.access_key,
                "number": invoice.number,
                "series": invoice.series,
                "supplier_name": invoice.supplier_name,
                "supplier_cnpj": invoice.supplier_cnpj,
                "total_invoice": float(invoice.total_invoice) if invoice.total_invoice else 0.0,
                "status": invoice.status,
            },
        )
        logger.info(f"Notificação disparada para nova NF-e {invoice.id} ({number_label})")
    except Exception as e:
        logger.error(f"Erro ao disparar notificação de nova NF-e {getattr(invoice, 'id', None)}: {e}")
