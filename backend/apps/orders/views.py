import django_filters
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.core.access import is_tenant_admin
from apps.core.permissions import effective_permission_codes
from apps.menu.models import Product
from apps.orders.models import Order, OrderBatch, OrderItem
from apps.printers.models import ScaleReading
from apps.orders.serializers import OrderBatchSerializer, OrderItemSerializer, OrderSerializer
from apps.orders.services import (
    add_order_item,
    cancel_order,
    close_order,
    comp_order_item,
    create_order,
    create_order_with_item,
    send_order_to_kitchen,
    update_order_item_status,
    void_order_item,
)
from apps.restaurants.models import Command

User = get_user_model()


def _can_authorize_order_cancellation(request, order):
    """Valida a autorização no mesmo request que altera o pedido.

    A senha nunca entra na fila offline: cancelamento exige resposta imediata
    do servidor, evitando guardar credenciais em texto puro no terminal.
    """

    cash_password = str(request.data.get("cash_password") or "")
    if cash_password:
        stored = order.restaurant.cash_action_password or ""
        return check_password(cash_password, stored) if stored else cash_password == "12345678"

    login = str(request.data.get("authorization_username") or "").strip()
    password = str(request.data.get("authorization_password") or "")
    if not login or not password:
        return False

    username = login
    if "@" in login:
        matched = (
            User.objects.filter(
                email__iexact=login,
                profile__account_id=order.account_id,
            )
            .only("username")
            .first()
        )
        if matched is not None:
            username = matched.get_username()
    authorizer = authenticate(request=request, username=username, password=password)
    if authorizer is None:
        return False
    profile = getattr(authorizer, "profile", None)
    if not profile or not profile.is_active or profile.account_id != order.account_id:
        return False
    codes = effective_permission_codes(authorizer)
    return is_tenant_admin(authorizer) or "*" in codes or "orders.cancel" in codes


class OrderFilterSet(django_filters.FilterSet):
    # Intervalo de datas por "aberto em" — comparação por data, inclusiva nas duas pontas.
    opened_after = django_filters.DateFilter(field_name="opened_at", lookup_expr="date__gte")
    opened_before = django_filters.DateFilter(field_name="opened_at", lookup_expr="date__lte")
    payment_pending = django_filters.BooleanFilter(method="filter_payment_pending")

    def filter_payment_pending(self, queryset, name, value):
        if value is True:
            return queryset.filter(
                payment_status__in=[Order.PAYMENT_PENDING, Order.PAYMENT_PARTIAL],
                status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            )
        return queryset

    class Meta:
        model = Order
        # restaurant/branch NÃO entram aqui: o escopo por tenant já os resolve
        # (TenantQuerySetMixin). Declará-los como filtro faz o django-filter validar
        # o UUID fora do contexto de tenant e devolver 400 "Faça uma escolha válida".
        fields = ["order_type", "status", "production_status", "payment_status", "table", "customer"]


class OrderViewSet(BaseTenantViewSet):
    serializer_class = OrderSerializer
    queryset = (
        Order.objects.select_related("restaurant", "branch", "table", "command", "customer", "delivery_address")
        .prefetch_related("items__product", "items__addons", "items__batch")
        .all()
    )
    filterset_class = OrderFilterSet
    search_fields = [
        "sequence_text",
        "customer__name",
        "table__number",
        "command__code",
        "command_number_text",
    ]
    ordering_fields = ["updated_at", "opened_at", "closed_at", "total", "sequence"]
    ordering = ["-updated_at"]

    def get_queryset(self):
        # A anotacao precisa ser aplicada aqui, e nao no `queryset` da classe:
        # o mixin de tenant remonta a consulta a partir do model e descartaria
        # qualquer annotate declarado la em cima.
        return (
            super()
            .get_queryset()
            .annotate(
                sequence_text=Cast("sequence", CharField()),
                command_number_text=Cast("command__number", CharField()),
            )
        )

    @action(detail=False, methods=["post"], url_path="open-command")
    def open_command(self, request):
        """Abre (ou retoma) o pedido de uma comanda. Espelha `open_table`.

        Comanda livre → cria pedido (201). Comanda em uso → retoma o pedido aberto
        (200). Resolve o restaurante pela própria comanda (sem filtros).
        """
        command_id = request.data.get("command")
        if not command_id:
            return Response(
                {"detail": "Selecione uma comanda para abrir o pedido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        command = (
            Command.objects.select_related("restaurant")
            .filter(pk=command_id, account=getattr(request, "account", None), is_active=True)
            .first()
        )
        if command is None:
            return Response(
                {"detail": "A comanda selecionada não existe ou está inativa."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = getattr(request.user, "profile", None)
        from apps.core.access import is_tenant_admin

        if not is_tenant_admin(request.user) and getattr(profile, "restaurant_id", None) != command.restaurant_id:
            return Response(
                {"detail": "A comanda selecionada pertence a outro restaurante."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if command.current_order_id:
            existing = Order.objects.filter(
                pk=command.current_order_id,
                account=getattr(request, "account", None),
                restaurant=command.restaurant,
                status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            ).first()
            if existing:
                return Response(self.get_serializer(existing).data)

        try:
            order = create_order(
                restaurant=command.restaurant,
                branch=None,
                order_type=Order.TYPE_COMMAND,
                command=command,
                user=request.user,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="create-with-item")
    def create_with_item(self, request):
        """Creates the order and first item in one transaction.

        This is the waiter-app entry point: dismissing a picker never leaves an
        empty counter/delivery/takeaway/command order behind.
        """
        profile = getattr(request.user, "profile", None)
        restaurant = getattr(profile, "restaurant", None)
        if restaurant is None:
            return Response({"detail": "Usuário sem restaurante vinculado."}, status=status.HTTP_400_BAD_REQUEST)

        order_type = request.data.get("order_type")
        if order_type not in {Order.TYPE_COMMAND, Order.TYPE_COUNTER, Order.TYPE_DELIVERY, Order.TYPE_TAKEAWAY}:
            return Response({"order_type": "Tipo de pedido inválido."}, status=status.HTTP_400_BAD_REQUEST)

        command = None
        table = None
        if order_type == Order.TYPE_COMMAND:
            command = Command.objects.filter(
                pk=request.data.get("command"),
                restaurant=restaurant,
                is_active=True,
            ).first()
            if command is None:
                return Response({"command": "Selecione uma comanda válida."}, status=status.HTTP_400_BAD_REQUEST)
            if command.current_order_id:
                return Response(
                    {"detail": "A comanda já possui um pedido. Reabra-o para adicionar itens."},
                    status=status.HTTP_409_CONFLICT,
                )
            if request.data.get("table"):
                from apps.restaurants.models import Table

                table = Table.objects.filter(
                    pk=request.data["table"],
                    restaurant=restaurant,
                    is_active=True,
                ).first()
                if table is None:
                    return Response({"table": "Selecione uma mesa válida."}, status=status.HTTP_400_BAD_REQUEST)

        raw_item = request.data.get("item")
        if not isinstance(raw_item, dict) or not raw_item.get("product"):
            return Response({"item": "Adicione o primeiro item do pedido."}, status=status.HTTP_400_BAD_REQUEST)
        product = Product.objects.filter(pk=raw_item["product"], restaurants=restaurant, is_active=True).first()
        if product is None:
            return Response({"item": "O produto selecionado não está disponível."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = create_order_with_item(
                restaurant=restaurant,
                order_type=order_type,
                command=command,
                table=table,
                product=product,
                user=request.user,
                item_data={
                    "quantity": raw_item.get("quantity"),
                    "variations": raw_item.get("variations", []),
                    "addons": raw_item.get("addons", []),
                    "customer_note": raw_item.get("customer_note", ""),
                    "expected_unit_price": raw_item.get("expected_unit_price"),
                },
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        user = self.request.user
        profile = getattr(user, "profile", None)
        restaurant = serializer.validated_data.get("restaurant") or profile.restaurant
        branch = None
        order = create_order(
            restaurant=restaurant,
            branch=branch,
            order_type=serializer.validated_data["order_type"],
            user=user,
            table=serializer.validated_data.get("table"),
            command=serializer.validated_data.get("command"),
            customer=serializer.validated_data.get("customer"),
            delivery_address=serializer.validated_data.get("delivery_address"),
            delivery_fee=serializer.validated_data.get("delivery_fee", 0),
            general_notes=serializer.validated_data.get("general_notes", ""),
        )
        serializer.instance = order

    @action(detail=True, methods=["get", "post"], url_path="items")
    def items(self, request, pk=None):
        order = self.get_object()
        if request.method == "GET":
            serializer = OrderItemSerializer(order.items.all(), many=True)
            return Response(serializer.data)

        product = Product.objects.get(
            Q(restaurants=order.restaurant),
            pk=request.data["product"],
        )
        scale_reading = None
        if request.data.get("scale_reading"):
            try:
                scale_reading = ScaleReading.objects.select_related("scale").get(
                    pk=request.data["scale_reading"],
                    account=order.account,
                )
            except ScaleReading.DoesNotExist:
                return Response({"detail": "Leitura de balanca nao encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            item = add_order_item(
                order=order,
                product=product,
                quantity=request.data.get("quantity"),
                user=request.user,
                variations=request.data.get("variations", []),
                addons=request.data.get("addons", []),
                customer_note=request.data.get("customer_note", ""),
                scale_reading=scale_reading,
                weight_kg=request.data.get("weight_kg"),
                expected_unit_price=request.data.get("expected_unit_price"),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"items/(?P<item_pk>[^/.]+)/void")
    def void_item(self, request, pk=None, item_pk=None):
        """Void a pending item (cancel before sending to kitchen)."""
        try:
            item = OrderItem.objects.get(pk=item_pk, order=self.get_object())
            item = void_order_item(item, request.user, reason=request.data.get("reason", ""))
        except OrderItem.DoesNotExist:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderItemSerializer(item).data)

    @action(detail=True, methods=["post"], url_path=r"items/(?P<item_pk>[^/.]+)/comp")
    def comp_item(self, request, pk=None, item_pk=None):
        """Comp an in-production item (courtesy after sending to kitchen)."""
        try:
            item = OrderItem.objects.get(pk=item_pk, order=self.get_object())
            item = comp_order_item(item, request.user, reason=request.data.get("reason", ""))
        except OrderItem.DoesNotExist:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderItemSerializer(item).data)

    @action(detail=True, methods=["get"], url_path="batches")
    def batches(self, request, pk=None):
        """List all production rounds for an order."""
        order = self.get_object()
        batches = OrderBatch.objects.filter(order=order).prefetch_related("items__product")
        serializer = OrderBatchSerializer(batches, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="send-to-kitchen")
    def send_to_kitchen(self, request, pk=None):
        try:
            order = send_order_to_kitchen(self.get_object(), request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        try:
            order = close_order(
                self.get_object(),
                request.user,
                discount=request.data.get("discount", 0),
                service_fee=request.data.get("service_fee"),
                service_fee_enabled=request.data.get("service_fee_enabled"),
                expected_total=request.data.get("expected_total"),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        from apps.payments.services import register_payment
        from apps.payments.serializers import PaymentSerializer

        try:
            payment = register_payment(
                order=self.get_object(),
                user=request.user,
                payment_method_id=request.data["payment_method"],
                amount=request.data["amount"],
                idempotency_key=request.headers.get("Idempotency-Key") or request.data.get("idempotency_key"),
                metadata=request.data.get("metadata", {}),
                cash_register_id=request.data.get("cash_register"),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="payments")
    def payments(self, request, pk=None):
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer

        order = self.get_object()
        payments = Payment.objects.filter(order=order, status=Payment.STATUS_APPROVED).order_by("created_at")
        return Response(PaymentSerializer(payments, many=True).data)

    @action(detail=True, methods=["delete"], url_path=r"payments/(?P<payment_pk>[^/.]+)")
    def delete_payment(self, request, pk=None, payment_pk=None):
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer
        from apps.payments.services import cancel_payment

        payment = Payment.objects.filter(
            pk=payment_pk,
            order=self.get_object(),
            status=Payment.STATUS_APPROVED,
        ).first()
        if payment is None:
            return Response({"detail": "Pagamento não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        try:
            payment = cancel_payment(payment=payment, user=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentSerializer(payment).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        order = self.get_object()
        if not _can_authorize_order_cancellation(request, order):
            return Response(
                {
                    "detail": (
                        "Informe a senha de operação do restaurante ou as "
                        "credenciais de um usuário com permissão para cancelar pedidos."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            order = cancel_order(order, request.user, request.data.get("reason", ""))
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="print")
    def print_order(self, request, pk=None):
        from apps.printers.models import Printer
        from apps.printers.services import register_print_job

        order = self.get_object()
        printer = None
        printer_id = request.data.get("printer")
        if printer_id:
            printer = Printer.objects.filter(
                pk=printer_id,
                account=order.account,
                restaurant=order.restaurant,
                is_active=True,
            ).first()
            if printer is None:
                return Response(
                    {"detail": "A impressora selecionada não existe, está inativa ou pertence a outro restaurante."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        job = register_print_job(
            order=order,
            user=request.user,
            job_type=request.data.get("job_type", "receipt"),
            printer=printer,
            manual_only=bool(request.data.get("manual_only", False)),
        )
        printer = job.printer
        return Response(
            {
                "print_job_id": str(job.id),
                "html": job.html_content,
                "status": job.status,
                "printer": (
                    {
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
                    }
                    if printer
                    else None
                ),
            }
        )


class OrderItemViewSet(BaseTenantViewSet):
    serializer_class = OrderItemSerializer
    queryset = (
        OrderItem.objects.select_related("restaurant", "branch", "order__table", "order__command", "product", "batch")
        .prefetch_related("addons")
        .all()
    )
    filterset_fields = ["order", "production_sector", "status"]
    search_fields = ["product__name", "customer_note"]
    ordering_fields = ["launched_at", "ready_at"]

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        try:
            item = update_order_item_status(
                self.get_object(),
                request.data["status"],
                request.user,
                reason=request.data.get("reason", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(item).data)
