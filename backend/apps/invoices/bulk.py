from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.invoices.models import Invoice
from apps.invoices.services import resend_fiscal_invoice


class BulkInvoiceResendSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        max_length=100,
    )


class InvoiceBulkResendMixin:
    ordering_fields = ["created_at", "issued_at", "number", "status", "emission_type", "total_amount"]
    ordering = ["-created_at", "-pk"]

    @action(detail=False, methods=["post"], url_path="bulk-resend")
    def bulk_resend(self, request):
        """Reenvia as notas escolhidas sem retransmitir documentos finalizados."""
        payload = BulkInvoiceResendSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(payload.validated_data["ids"]))
        invoices = {invoice.pk: invoice for invoice in self.get_queryset().filter(pk__in=ids)}
        result = {
            "requested": len(ids),
            "resent": 0,
            "skipped_issued": 0,
            "skipped_cancelled": 0,
            "failed": 0,
            "errors": [],
        }
        for invoice_id in ids:
            invoice = invoices.get(invoice_id)
            if invoice is None:
                self._add_bulk_error(result, invoice_id, "Nota fiscal nao encontrada.")
                continue
            if invoice.status == Invoice.STATUS_ISSUED:
                result["skipped_issued"] += 1
                continue
            if invoice.status == Invoice.STATUS_CANCELLED:
                result["skipped_cancelled"] += 1
                continue
            try:
                resent = resend_fiscal_invoice(invoice, user=request.user)
            except ValidationError as exc:
                self._add_bulk_error(result, invoice_id, exc.messages[0])
                continue
            if resent.status == Invoice.STATUS_ERROR:
                message = resent.error_message or "A Focus rejeitou o reenvio da nota."
                self._add_bulk_error(result, invoice_id, message)
                continue
            result["resent"] += 1
        return Response(result)

    @staticmethod
    def _add_bulk_error(result, invoice_id, message):
        result["failed"] += 1
        result["errors"].append({"id": str(invoice_id), "message": message})
