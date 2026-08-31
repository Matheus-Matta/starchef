import secrets

from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.modules import MODULE_FINANCEIRO
from apps.core.access import is_tenant_admin
from apps.core.viewsets import BaseTenantViewSet
from apps.invoices.focus import (
    FocusCompanySyncResult,
    FocusNfeApiError,
    FocusNfeConfigurationError,
    delete_focus_company,
    enqueue_focus_company_sync,
    get_account_focus_config,
    refresh_focus_company,
    sync_focus_company,
)
from apps.invoices.cosmos import (
    CosmosApiError,
    CosmosConfigurationError,
    cosmos_config_status,
    suggest_fiscal_profile,
)
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice
from apps.invoices.providers import FocusNfeProvider, get_provider
from apps.invoices.serializers import FiscalConfigSerializer, FiscalProfileSerializer, InvoiceSerializer
from apps.invoices.services import (
    cancel_fiscal_invoice,
    emit_fiscal_invoice,
    ensure_fiscal_config,
    fiscal_emission_unavailable_reason,
    print_fiscal_invoice,
    resend_fiscal_invoice,
)
from apps.restaurants.models import Restaurant


class FiscalProfileViewSet(BaseTenantViewSet):
    """Grupos tributarios (CFOP/CSOSN/NCM + aliquotas) reutilizados pelos produtos.

    Cadastro da CONTA, compartilhado entre restaurantes (ver `FiscalProfile`):
    o payload nao precisa mandar restaurante/filial — eles ficam nulos.
    """

    required_module = MODULE_FINANCEIRO
    serializer_class = FiscalProfileSerializer
    queryset = FiscalProfile.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["is_active", "is_default"]
    search_fields = ["name", "ncm", "cfop", "csosn", "cest"]
    ordering_fields = ["name", "ncm", "cfop", "created_at"]
    ordering = ["name"]

    @action(detail=False, methods=["get"], url_path="cosmos-status")
    def cosmos_status(self, request):
        """Estado nao sensivel usado pelo formulario de perfil fiscal."""

        return Response(cosmos_config_status(getattr(request, "account", None)))

    @action(detail=False, methods=["get"], url_path="cosmos-suggest")
    def cosmos_suggest(self, request):
        """Sugere NCM/CEST pelo nome sem gravar nem sobrescrever o perfil."""

        query = str(request.query_params.get("query") or "").strip()
        try:
            suggestion = suggest_fiscal_profile(getattr(request, "account", None), query)
        except CosmosConfigurationError as exc:
            return Response(
                {"error": {"code": "cosmos_not_configured", "message": str(exc)}, "detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except CosmosApiError as exc:
            response_status = status.HTTP_400_BAD_REQUEST
            if exc.error_code == "cosmos_not_found":
                response_status = status.HTTP_404_NOT_FOUND
            elif exc.error_code == "cosmos_rate_limited":
                response_status = status.HTTP_429_TOO_MANY_REQUESTS
            elif exc.retryable:
                response_status = status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(
                {
                    "error": {"code": exc.error_code, "message": str(exc)},
                    "detail": str(exc),
                    "cosmos_status_code": exc.upstream_status,
                },
                status=response_status,
            )
        return Response(suggestion.as_response())


class FiscalConfigViewSet(BaseTenantViewSet):
    """Configuracao fiscal por filial (emitente + parametros de emissao)."""

    required_module = MODULE_FINANCEIRO
    serializer_class = FiscalConfigSerializer
    queryset = FiscalConfig.objects.select_related(
        "account__focus_nfe_config", "restaurant", "branch", "default_profile"
    ).all()
    filterset_fields = ["is_active", "document_model"]

    @action(detail=False, methods=["get"], url_path="for-restaurant")
    def for_restaurant(self, request):
        """A configuracao fiscal de um restaurante, criando-a se ainda nao existir.

        A tela avancada (Restaurantes > acoes > Configuracao fiscal / Focus NFe)
        entra por aqui em vez de listar e dar POST: era esse POST concorrente
        com o cadastro do restaurante que estourava a
        `unique_fiscal_config_by_branch` como "valor duplicado".
        """
        restaurant_id = request.query_params.get("restaurant")
        if not restaurant_id:
            return Response({"detail": "Informe o restaurante em ?restaurant=."}, status=status.HTTP_400_BAD_REQUEST)

        restaurant = self._scoped_restaurant(restaurant_id)
        if restaurant is None:
            return Response({"detail": "Restaurante nao encontrado."}, status=status.HTTP_404_NOT_FOUND)

        config = ensure_fiscal_config(restaurant, user=request.user)
        if config is None:
            return Response(
                {"detail": "Este restaurante ainda nao tem uma filial para receber a configuracao fiscal."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(config).data)

    def _scoped_restaurant(self, restaurant_id):
        """Restaurante da conta do request, respeitando o recorte do perfil."""
        account = getattr(self.request, "account", None)
        if account is None:
            return None
        queryset = Restaurant.objects.filter(account=account)
        profile = getattr(self.request.user, "profile", None)
        if not is_tenant_admin(self.request.user):
            if profile is None or not profile.restaurant_id:
                return None
            queryset = queryset.filter(pk=profile.restaurant_id)
        try:
            return queryset.filter(pk=restaurant_id).first()
        except (ValidationError, ValueError):
            # id malformado na querystring: e "nao encontrado", nao um 500.
            return None

    def perform_create(self, serializer):
        super().perform_create(serializer)
        enqueue_focus_company_sync(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        enqueue_focus_company_sync(serializer.instance)

    def _focus_action(self, operation):
        config = self.get_object()
        try:
            result = operation(config)
        except FocusNfeConfigurationError as exc:
            config.refresh_from_db()
            return Response(
                {
                    "synced": False,
                    "error": {
                        "code": "focus_not_configured",
                        "message": f"Empresa nao sincronizada: {exc}",
                    },
                    "message": f"Empresa nao sincronizada: {exc}",
                    "config": self.get_serializer(config).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except FocusNfeApiError as exc:
            config.refresh_from_db()
            response_status = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "synced": False,
                    "error": {"code": exc.error_code, "message": str(exc)},
                    "message": str(exc),
                    "focus_status_code": exc.upstream_status,
                    "config": self.get_serializer(config).data,
                },
                status=response_status,
            )
        if isinstance(result, FocusCompanySyncResult):
            return Response(
                {
                    "synced": result.synced,
                    "dry_run": result.dry_run,
                    "operation": result.operation,
                    "message": result.message,
                    "warnings": list(result.warnings),
                    "config": self.get_serializer(result.config).data,
                }
            )
        config.refresh_from_db()
        return Response(self.get_serializer(config).data)

    @action(detail=True, methods=["post"], url_path="focus-sync")
    def focus_sync(self, request, pk=None):
        return self._focus_action(sync_focus_company)

    @action(detail=True, methods=["post"], url_path="focus-refresh")
    def focus_refresh(self, request, pk=None):
        return self._focus_action(refresh_focus_company)

    @action(detail=True, methods=["delete"], url_path="focus-company")
    def focus_company_delete(self, request, pk=None):
        config = self.get_object()
        if not is_tenant_admin(request.user):
            return Response(
                {"detail": "Apenas administradores podem excluir uma empresa da Focus NFe."},
                status=status.HTTP_403_FORBIDDEN,
            )
        confirmation = "".join(filter(str.isdigit, str(request.data.get("confirm_cnpj", ""))))
        expected = "".join(filter(str.isdigit, config.cnpj))
        if not expected or confirmation != expected:
            return Response(
                {"detail": "Confirme a exclusao informando o CNPJ completo em confirm_cnpj."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._focus_action(delete_focus_company)


class InvoiceViewSet(BaseTenantViewSet):
    required_module = MODULE_FINANCEIRO
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.select_related("restaurant", "branch", "order").prefetch_related("items").all()
    filterset_fields = ["status", "phase", "document_model", "order"]
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

        unavailable_reason = fiscal_emission_unavailable_reason(order)
        if unavailable_reason:
            return Response(
                {
                    "emitted": False,
                    "message": f"Nota fiscal nao emitida: {unavailable_reason}",
                },
                status=status.HTTP_200_OK,
            )

        # O pedido pago ja emite sozinho (`order_fully_paid`). Quando o PDV
        # pede a emissao logo depois, a nota do pedido ja existe — e devolver
        # 400 aqui fazia o caixa ver "Pedido ja possui nota fiscal emitida"
        # numa venda que deu certo. Emitir e idempotente por pedido: a nota
        # que existe E a resposta.
        existing = getattr(order, "invoice", None)
        if existing and existing.status in (Invoice.STATUS_PENDING, Invoice.STATUS_ISSUED):
            data = InvoiceSerializer(existing, context={"request": request}).data
            data["emitted"] = True
            return Response(data, status=status.HTTP_200_OK)

        try:
            invoice = emit_fiscal_invoice(
                order,
                cpf=request.data.get("cpf"),
                cpf_name=request.data.get("cpf_name", ""),
                user=request.user,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        data = InvoiceSerializer(invoice, context={"request": request}).data
        data["emitted"] = True
        return Response(data, status=status.HTTP_201_CREATED)

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

        job = print_fiscal_invoice(invoice, user=request.user, printer=printer, manual_only=True)
        return Response(
            {"print_job_id": str(job.id), "status": job.status, "html": job.html_content},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancela a nota (transmissao do evento a SEFAZ e a parte externa/em branco)."""
        invoice = cancel_fiscal_invoice(self.get_object(), reason=request.data.get("reason", ""), user=request.user)
        return self._serialize(invoice)

    @action(detail=True, methods=["post"], url_path="refresh-status")
    def refresh_status(self, request, pk=None):
        invoice = self.get_object()
        try:
            get_provider(invoice.provider).status(invoice)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        invoice.updated_by = request.user
        invoice.save()
        return self._serialize(invoice)

    @action(detail=True, methods=["post"], url_path="resend")
    def resend(self, request, pk=None):
        """Retransmite somente a nota escolhida, sem varrer as demais pendentes."""
        try:
            invoice = resend_fiscal_invoice(self.get_object(), user=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        data = InvoiceSerializer(invoice, context={"request": request}).data
        data["resent"] = invoice.status != Invoice.STATUS_ERROR
        if invoice.status == Invoice.STATUS_ERROR:
            message = invoice.error_message or "A Focus rejeitou o reenvio da nota."
            return Response(
                {
                    "resent": False,
                    "error": {"code": "fiscal_resend_rejected", "message": message},
                    "invoice": data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(data)


class FocusNfeWebhookView(APIView):
    """Recebe atualizacoes assincronas da Focus (principalmente NF-e modelo 55)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        document = payload.get("nfe") if isinstance(payload.get("nfe"), dict) else payload
        reference = document.get("ref") or document.get("referencia") or payload.get("ref")
        invoice = (
            Invoice.all_objects.select_related("account").filter(provider_reference=reference).first()
            if reference
            else None
        )
        if invoice is None:
            return Response({"detail": "Nota fiscal nao encontrada."}, status=status.HTTP_404_NOT_FOUND)
        account_config = get_account_focus_config(invoice.account)
        expected = getattr(account_config, "webhook_authorization", "")
        header = getattr(account_config, "webhook_authorization_header", "") or "Authorization"
        received = request.headers.get(header, "")
        if not expected or not secrets.compare_digest(str(received), str(expected)):
            return Response({"detail": "Webhook Focus NFe nao autorizado."}, status=status.HTTP_403_FORBIDDEN)
        try:
            FocusNfeProvider().apply_response(invoice, document)
        except RuntimeError:
            # Rejeicoes tambem sao estados finais validos do webhook e precisam
            # ser persistidas, sem pedir reenvio infinito para a Focus.
            pass
        invoice.save()
        return Response({"ok": True})
