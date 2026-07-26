from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.modules import MODULE_FINANCEIRO
from apps.core.viewsets import BaseTenantViewSet
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice
from apps.invoices.serializers import FiscalConfigSerializer, FiscalProfileSerializer, InvoiceSerializer
from apps.invoices.services import cancel_fiscal_invoice, emit_fiscal_invoice, print_fiscal_invoice


class FiscalProfileViewSet(BaseTenantViewSet):
    """Grupos tributarios (CFOP/CSOSN/NCM + aliquotas) reutilizados pelos produtos."""

    required_module = MODULE_FINANCEIRO
    serializer_class = FiscalProfileSerializer
    queryset = FiscalProfile.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["is_active", "is_default"]
    search_fields = ["name", "ncm", "cfop"]


class FiscalConfigViewSet(BaseTenantViewSet):
    """Configuracao fiscal por filial (emitente + parametros de emissao)."""

    required_module = MODULE_FINANCEIRO
    serializer_class = FiscalConfigSerializer
    queryset = FiscalConfig.objects.select_related("restaurant", "branch", "default_profile").all()
    filterset_fields = ["is_active", "document_model"]


class InvoiceViewSet(BaseTenantViewSet):
    required_module = MODULE_FINANCEIRO
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.select_related("restaurant", "branch", "order").prefetch_related("items").all()
    filterset_fields = ["status", "phase", "document_model"]
    search_fields = ["number", "provider", "access_key"]

    def _account(self):
        return getattr(self.request, "account", None)

    def _serialize(self, invoice, code=status.HTTP_200_OK):
        return Response(InvoiceSerializer(invoice, context={"request": self.request}).data, status=code)

    @action(detail=False, methods=["post"], url_path="emit")
    def emit(self, request):
        """Emite (monta) a nota fiscal de um pedido: POST { order, cpf?, cpf_name? }."""
        from apps.orders.models import Order

        orders = Order.objects.all()
        if self._account():
            orders = orders.filter(account=self._account())
        order = orders.filter(pk=request.data.get("order")).first()
        if not order:
            return Response({"detail": "Pedido nao encontrado."}, status=status.HTTP_404_NOT_FOUND)

        try:
            invoice = emit_fiscal_invoice(
                order,
                cpf=request.data.get("cpf"),
                cpf_name=request.data.get("cpf_name", ""),
                user=request.user,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return self._serialize(invoice, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="print")
    def print_danfe(self, request, pk=None):
        """Gera o cupom DANFE (PrintJob) para a nota."""
        from apps.printers.models import Printer

        invoice = self.get_object()
        printer = None
        if request.data.get("printer"):
            printer_qs = Printer.objects.all()
            if self._account():
                printer_qs = printer_qs.filter(account=self._account())
            printer = printer_qs.filter(pk=request.data["printer"]).first()

        job = print_fiscal_invoice(invoice, user=request.user, printer=printer)
        return Response(
            {"print_job_id": str(job.id), "status": job.status, "html": job.html_content},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancela a nota (transmissao do evento a SEFAZ e a parte externa/em branco)."""
        invoice = cancel_fiscal_invoice(self.get_object(), reason=request.data.get("reason", ""), user=request.user)
        return self._serialize(invoice)
