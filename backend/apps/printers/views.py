from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.orders.serializers import OrderItemSerializer
from apps.printers.models import Printer, PrintJob, Scale, ScaleReading
from apps.printers.serializers import (
    PrinterSerializer,
    PrintJobSerializer,
    ScaleReadingSerializer,
    ScaleSerializer,
)
from apps.printers.services import weigh_to_order


class PrinterViewSet(BaseTenantViewSet):
    serializer_class = PrinterSerializer
    queryset = Printer.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "driver_type", "sector", "is_active"]
    search_fields = ["name", "endpoint"]


class ScaleViewSet(BaseTenantViewSet):
    serializer_class = ScaleSerializer
    queryset = Scale.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "protocol", "is_active"]
    search_fields = ["name", "port"]

    @action(detail=True, methods=["get"], url_path="latest-reading")
    def latest_reading(self, request, pk=None):
        """Ultima leitura valida da balanca, respeitando reading_max_age_seconds. Usada pelo PDV."""
        scale = self.get_object()
        cutoff = timezone.now() - timedelta(seconds=scale.reading_max_age_seconds)
        reading = (
            ScaleReading.objects.filter(scale=scale, created_at__gte=cutoff, order_item__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if reading is None:
            return Response(
                {"detail": "Nenhuma leitura recente da balanca. Coloque o prato e aguarde, ou digite o peso."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ScaleReadingSerializer(reading, context={"request": request}).data)

    def _resolve_order(self, scale, order_id):
        """Pedido informado no corpo ou, na ausencia, o pedido vinculado a balanca."""
        from apps.orders.models import Order

        if order_id:
            return Order.objects.filter(pk=order_id, account=scale.account).first()
        return scale.active_order

    @action(detail=True, methods=["post"], url_path="bind-order")
    def bind_order(self, request, pk=None):
        """Vincula (ou desvincula com order=null) um pedido a balanca para o gatilho automatico."""
        scale = self.get_object()
        scale.active_order = self._resolve_order(scale, request.data.get("order"))
        scale.updated_by = request.user
        scale.save(update_fields=["active_order", "updated_by", "updated_at"])
        return Response(ScaleSerializer(scale, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="weigh")
    def weigh(self, request, pk=None):
        """Confirmacao a partir do PDV: pesa -> lanca o item por kg -> gera a nota de pesagem."""
        scale = self.get_object()
        order = self._resolve_order(scale, request.data.get("order"))
        if order is None:
            return Response({"detail": "Informe um pedido ou vincule um pedido a balanca."}, status=status.HTTP_400_BAD_REQUEST)

        reading = None
        if request.data.get("scale_reading"):
            reading = ScaleReading.objects.filter(pk=request.data["scale_reading"], account=scale.account).first()

        try:
            item, job = weigh_to_order(
                scale=scale,
                order=order,
                user=request.user,
                scale_reading=reading,
                weight_kg=request.data.get("weight_kg"),
                do_print=request.data.get("print", True),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "item": OrderItemSerializer(item).data,
                "print_job": PrintJobSerializer(job, context={"request": request}).data if job else None,
            },
            status=status.HTTP_201_CREATED,
        )


class ScaleReadingViewSet(BaseTenantViewSet):
    """POST usado pelo agente local para enviar leituras da balanca."""

    serializer_class = ScaleReadingSerializer
    queryset = ScaleReading.objects.select_related("restaurant", "branch", "scale").all()
    filterset_fields = ["restaurant", "branch", "scale", "source", "is_stable"]
    ordering_fields = ["created_at"]
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        # Leituras herdam restaurante/filial da balanca: o agente so envia scale + peso.
        scale = serializer.validated_data.get("scale")
        if scale is not None:
            serializer.validated_data.setdefault("restaurant", scale.restaurant)
            serializer.validated_data.setdefault("branch", scale.branch)
        super().perform_create(serializer)
        self._maybe_auto_weigh(serializer.instance)

    def _maybe_auto_weigh(self, reading):
        """Gatilho automatico: leitura estavel + balanca com auto_print/produto/pedido -> nota."""
        scale = reading.scale
        if not scale or not scale.auto_print or not reading.is_stable:
            return
        if not scale.active_order_id or not scale.product_id:
            return

        from apps.orders.models import Order

        order = Order.objects.filter(pk=scale.active_order_id).first()
        if not order or order.is_locked:
            return
        try:
            weigh_to_order(scale=scale, order=order, user=self.request.user, scale_reading=reading, do_print=True)
        except ValidationError:
            pass  # nunca impede o registro da leitura em si


class PrintJobViewSet(BaseTenantViewSet):
    serializer_class = PrintJobSerializer
    queryset = PrintJob.objects.select_related("restaurant", "branch", "printer", "order", "printed_by").all()
    filterset_fields = ["restaurant", "branch", "printer", "job_type", "status"]
    ordering_fields = ["created_at", "printed_at"]

    @action(detail=True, methods=["post"], url_path="mark-printed")
    def mark_printed(self, request, pk=None):
        """Chamada pelo agente local apos imprimir com sucesso."""
        job = self.get_object()
        job.status = PrintJob.STATUS_PRINTED
        job.printed_at = timezone.now()
        job.printed_by = request.user
        job.error_message = ""
        job.save(update_fields=["status", "printed_at", "printed_by", "error_message", "updated_at"])
        return Response(PrintJobSerializer(job, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="mark-failed")
    def mark_failed(self, request, pk=None):
        """Chamada pelo agente quando a impressao falha (registra o erro)."""
        job = self.get_object()
        job.status = PrintJob.STATUS_FAILED
        job.error_message = str(request.data.get("error", ""))[:2000]
        job.save(update_fields=["status", "error_message", "updated_at"])
        return Response(PrintJobSerializer(job, context={"request": request}).data)

