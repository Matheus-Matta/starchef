from datetime import timedelta
from hashlib import sha256

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.template.loader import get_template
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.core.viewsets import BaseTenantViewSet
from apps.core.permissions import CanOperateScale, CanUseOrManageDevices
from apps.orders.serializers import OrderItemSerializer
from apps.printers.models import Printer, PrintJob, Scale, ScaleReading
from apps.printers.serializers import (
    PrinterSerializer,
    PrintJobSerializer,
    ScaleReadingSerializer,
    ScaleSerializer,
)
from apps.printers.services import weigh_to_order


class DevicePollingRateThrottle(UserRateThrottle):
    scope = "device_poll"


class PrinterViewSet(BaseTenantViewSet):
    permission_classes = [CanUseOrManageDevices]
    serializer_class = PrinterSerializer
    queryset = Printer.objects.select_related("restaurant", "branch", "sector").all()
    filterset_fields = ["restaurant", "driver_type", "sector", "is_active"]
    search_fields = ["name", "endpoint"]

    @action(detail=False, methods=["get"], url_path="templates")
    def templates(self, request):
        """Modelos oficiais baixados e armazenados pelo agente desktop."""
        definitions = {
            "receipt": ("printers/receipt.html", ["receipt", "table_bill", "cash_close"]),
            "kitchen_ticket": ("printers/kitchen_ticket.html", ["kitchen_ticket", "bar_ticket"]),
            "weigh_ticket": ("printers/weigh_ticket.html", ["weigh_ticket"]),
            "danfe_nfce": ("printers/danfe_nfce.html", ["fiscal_danfe"]),
        }
        templates = []
        for key, (template_name, job_types) in definitions.items():
            source = get_template(template_name).template.source
            templates.append(
                {
                    "key": key,
                    "template_name": template_name,
                    "job_types": job_types,
                    "version": sha256(source.encode("utf-8")).hexdigest(),
                    "content": source,
                }
            )
        return Response({"templates": templates})

    @action(detail=True, methods=["post"], url_path="test-connection")
    def test_connection(self, request, pk=None):
        """Cria uma nota diagnóstica para impressão manual no PDV Desktop."""
        from apps.printers.services import register_printer_test_job

        printer = self.get_object()
        job = register_printer_test_job(printer=printer, user=request.user)
        return Response(
            {
                "print_job_id": str(job.id),
                "status": job.status,
                "html": job.html_content,
                "payload": job.payload,
                "printer": {
                    "id": str(printer.id),
                    "name": printer.name,
                    "endpoint": printer.endpoint,
                    "connection_type": printer.connection_type,
                    "host": printer.host,
                    "port": printer.port,
                    "timeout_seconds": printer.timeout_seconds,
                    "driver_type": printer.driver_type,
                    "settings": printer.settings,
                    "auto_print": printer.auto_print,
                    "is_active": printer.is_active,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class ScaleViewSet(BaseTenantViewSet):
    permission_classes = [CanUseOrManageDevices]
    serializer_class = ScaleSerializer
    queryset = Scale.objects.select_related("restaurant", "branch", "sector").all()
    filterset_fields = ["restaurant", "protocol", "is_active"]
    search_fields = ["name", "port"]

    def get_permissions(self):
        if self.action == "checkout_command":
            return [CanOperateScale()]
        if self.action in {"claim_agent", "release_agent"}:
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_throttles(self):
        if self.action in {"latest_reading", "claim_agent", "release_agent"}:
            return [DevicePollingRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=["post"], url_path="claim-agent")
    def claim_agent(self, request, pk=None):
        """Concede uma posse curta e exclusiva da leitura a um PDV Desktop."""
        instance_id = str(request.data.get("instance_id", "")).strip()[:120]
        if not instance_id:
            return Response(
                {"detail": "Identificador do PDV não informado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        now = timezone.now()
        lease_seconds = 15
        with transaction.atomic():
            scale = Scale.objects.select_for_update().get(pk=self.get_object().pk)
            owned_by_other = (
                scale.agent_instance_id
                and scale.agent_instance_id != instance_id
                and scale.agent_lease_expires_at
                and scale.agent_lease_expires_at > now
            )
            if owned_by_other:
                return Response(
                    {
                        "claimed": False,
                        "detail": "Esta balança está sendo monitorada por outro PDV.",
                        "lease_expires_at": scale.agent_lease_expires_at,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            scale.agent_instance_id = instance_id
            scale.agent_lease_expires_at = now + timedelta(seconds=lease_seconds)
            scale.updated_by = request.user
            scale.save(
                update_fields=[
                    "agent_instance_id",
                    "agent_lease_expires_at",
                    "updated_by",
                    "updated_at",
                ]
            )
        return Response(
            {
                "claimed": True,
                "lease_seconds": lease_seconds,
                "lease_expires_at": scale.agent_lease_expires_at,
            }
        )

    @action(detail=True, methods=["post"], url_path="release-agent")
    def release_agent(self, request, pk=None):
        instance_id = str(request.data.get("instance_id", "")).strip()[:120]
        with transaction.atomic():
            scale = Scale.objects.select_for_update().get(pk=self.get_object().pk)
            if scale.agent_instance_id == instance_id:
                scale.agent_instance_id = ""
                scale.agent_lease_expires_at = None
                scale.updated_by = request.user
                scale.save(
                    update_fields=[
                        "agent_instance_id",
                        "agent_lease_expires_at",
                        "updated_by",
                        "updated_at",
                    ]
                )
        return Response({"released": True})

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

    @action(detail=True, methods=["post"], url_path="checkout-command")
    def checkout_command(self, request, pk=None):
        """Finaliza uma pesagem na comanda e inclui extras em uma transacao."""
        from apps.menu.models import Product
        from apps.orders.models import Order
        from apps.orders.serializers import OrderSerializer
        from apps.orders.services import add_order_item, create_order, recalculate_order
        from apps.printers.services import register_weigh_print
        from apps.restaurants.models import Command

        command_code = str(request.data.get("command_code", "")).strip()
        reading_id = request.data.get("scale_reading")
        extras = request.data.get("extras") or []
        if not command_code:
            return Response({"detail": "Leia ou informe o codigo da comanda."}, status=status.HTTP_400_BAD_REQUEST)
        if not reading_id:
            return Response({"detail": "A leitura da balanca e obrigatoria."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(extras, list) or len(extras) > 20:
            return Response({"detail": "Informe no maximo 20 produtos adicionais."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                scale = Scale.objects.select_for_update().get(pk=self.get_object().pk)
                command_lookup = Q(code=command_code)
                if command_code.isdigit():
                    command_lookup |= Q(number=int(command_code))
                command = (
                    Command.objects.select_for_update()
                    .select_related("restaurant")
                    .filter(
                        command_lookup,
                        account=scale.account,
                        restaurant=scale.restaurant,
                        is_active=True,
                    )
                    .first()
                )
                if command is None:
                    raise ValidationError("Comanda nao encontrada para o restaurante selecionado.")

                order = None
                if command.current_order_id:
                    order = Order.objects.filter(
                        pk=command.current_order_id,
                        account=scale.account,
                        restaurant=scale.restaurant,
                        status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
                    ).first()
                if order is None:
                    order = create_order(
                        restaurant=scale.restaurant,
                        branch=None,
                        order_type=Order.TYPE_COMMAND,
                        command=command,
                        user=request.user,
                    )

                reading = (
                    ScaleReading.objects.select_for_update()
                    .filter(
                        pk=reading_id,
                        account=scale.account,
                        scale=scale,
                        is_stable=True,
                        order_item__isnull=True,
                    )
                    .first()
                )
                if reading is None:
                    raise ValidationError("Leitura invalida, instavel ou ja utilizada.")

                weighed_item, _ = weigh_to_order(
                    scale=scale,
                    order=order,
                    user=request.user,
                    scale_reading=reading,
                    do_print=False,
                )

                extra_items = []
                for entry in extras:
                    if not isinstance(entry, dict):
                        raise ValidationError("Produto adicional invalido.")
                    try:
                        quantity = int(entry.get("quantity", 1))
                    except (TypeError, ValueError) as exc:
                        raise ValidationError("Quantidade adicional invalida.") from exc
                    if quantity < 1 or quantity > 99:
                        raise ValidationError("A quantidade adicional deve ficar entre 1 e 99.")
                    product = Product.objects.filter(
                        Q(restaurants=scale.restaurant),
                        pk=entry.get("product"),
                        account=scale.account,
                        is_active=True,
                    ).first()
                    if product is None or product.is_weighed:
                        raise ValidationError("Produto adicional inexistente ou vendido por peso.")
                    variations = entry.get("variations") or []
                    if not isinstance(variations, list):
                        raise ValidationError("Variacao do adicional invalida.")
                    addons = entry.get("addons") or []
                    if not isinstance(addons, list):
                        raise ValidationError("Lista de adicionais invalida.")
                    customer_note = str(entry.get("customer_note") or "")
                    extra_items.append(
                        add_order_item(
                            order=order,
                            product=product,
                            quantity=quantity,
                            user=request.user,
                            variations=variations,
                            addons=addons,
                            customer_note=customer_note,
                        )
                    )

                # A nota deve ser um snapshot do pedido final, depois do item
                # pesado, dos extras e do recálculo explícito dos totais.
                order = recalculate_order(order)
                print_job = (
                    register_weigh_print(
                        order=order,
                        item=weighed_item,
                        scale=scale,
                        user=request.user,
                    )
                    if request.data.get("print", True)
                    else None
                )
                order = self._resolve_order(scale, order.id)
                return Response(
                    {
                        "order": OrderSerializer(order).data,
                        "weighed_item": OrderItemSerializer(weighed_item).data,
                        "extra_items": OrderItemSerializer(extra_items, many=True).data,
                        "print_job": (
                            PrintJobSerializer(print_job, context={"request": request}).data
                            if print_job
                            else None
                        ),
                    },
                    status=status.HTTP_201_CREATED,
                )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)


class ScaleReadingViewSet(BaseTenantViewSet):
    """POST usado pelo agente local para enviar leituras da balanca."""

    serializer_class = ScaleReadingSerializer
    queryset = ScaleReading.objects.select_related("restaurant", "branch", "scale").all()
    filterset_fields = ["scale", "source", "is_stable"]
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
        if not scale.product_id:
            return

        from apps.orders.models import Order
        from apps.orders.services import create_order

        order = None
        auto_created = False
        if scale.active_order_id:
            order = Order.objects.filter(
                pk=scale.active_order_id,
                account=scale.account,
                restaurant=scale.restaurant,
            ).first()
        if order is None or order.is_locked:
            order = create_order(
                restaurant=scale.restaurant,
                branch=None,
                order_type=Order.TYPE_COUNTER,
                user=self.request.user,
                general_notes=f"Pedido criado automaticamente pela balanca {scale.name}.",
            )
            auto_created = True
        try:
            weigh_to_order(scale=scale, order=order, user=self.request.user, scale_reading=reading, do_print=True)
            if auto_created:
                order.status = Order.STATUS_AWAITING_PAYMENT
                order.save(update_fields=["status", "updated_at"])
        except ValidationError:
            if auto_created:
                order.delete()
            # Nunca impede o registro da leitura em si. O agente tentara uma
            # nova leitura depois que o peso voltar a zero.


class PrintJobViewSet(BaseTenantViewSet):
    serializer_class = PrintJobSerializer
    queryset = PrintJob.objects.select_related("restaurant", "branch", "printer", "order", "printed_by").all()
    filterset_fields = ["restaurant", "printer", "job_type", "status"]
    ordering_fields = ["created_at", "printed_at"]

    def list(self, request, *args, **kwargs):
        # Compatibilidade operacional: libera qualquer rodada agendada por uma
        # versao anterior que ainda esteja pendente, mesmo sem Celery.
        from apps.orders.services import dispatch_due_kitchen_batches

        account = getattr(request, "account", None)
        if account is not None:
            dispatch_due_kitchen_batches(account_id=account.id)
        return super().list(request, *args, **kwargs)

    def get_throttles(self):
        if self.action == "list":
            return [DevicePollingRateThrottle()]
        return super().get_throttles()

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

    @action(detail=True, methods=["post"], url_path="requeue")
    def requeue(self, request, pk=None):
        """Reimprime este mesmo trabalho, sem criar outro pedido.

        Reenfileirar preserva o conteudo original — inclusive o layout da nota
        de pesagem e o Code 128 da comanda —, o que gerar um novo trabalho a
        partir do pedido nao faria. Nenhum item e recalculado nem duplicado:
        apenas o estado volta para `rendered` e o agente local imprime de novo.
        """
        with transaction.atomic():
            job = PrintJob.objects.select_for_update().get(pk=self.get_object().pk)
            # O agente local consome `pending` e `rendered`. Reenfileirar um
            # trabalho que ainda esta na fila produziria uma segunda impressao
            # silenciosa, entao so `printed` e `failed` podem ser repetidos.
            if job.status in {PrintJob.STATUS_PENDING, PrintJob.STATUS_RENDERED}:
                return Response(
                    {"detail": "Este cupom ainda esta aguardando impressao."},
                    status=status.HTTP_409_CONFLICT,
                )
            job.status = PrintJob.STATUS_RENDERED
            job.error_message = ""
            job.printed_at = None
            job.updated_by = request.user
            job.save(update_fields=["status", "error_message", "printed_at", "updated_by", "updated_at"])
        return Response(PrintJobSerializer(job, context={"request": request}).data)
