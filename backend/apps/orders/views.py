from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
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
    send_order_to_kitchen,
    update_order_item_status,
    void_order_item,
)


class OrderViewSet(BaseTenantViewSet):
    serializer_class = OrderSerializer
    queryset = (
        Order.objects.select_related("restaurant", "branch", "table", "command", "customer", "delivery_address")
        .prefetch_related("items__product", "items__addons", "items__batch")
        .all()
    )
    filterset_fields = ["restaurant", "branch", "order_type", "status", "production_status", "payment_status", "table", "customer"]
    search_fields = ["sequence", "customer__name", "table__number"]
    ordering_fields = ["opened_at", "closed_at", "total", "sequence"]

    def perform_create(self, serializer):
        user = self.request.user
        profile = getattr(user, "profile", None)
        restaurant = serializer.validated_data.get("restaurant") or profile.restaurant
        branch = serializer.validated_data.get("branch") or profile.branch
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

        product = Product.objects.get(pk=request.data["product"], restaurant=order.restaurant, branch=order.branch)
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
                customer_note=request.data.get("customer_note", ""),
                scale_reading=scale_reading,
                weight_kg=request.data.get("weight_kg"),
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
            return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)
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
            return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)
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
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="payments")
    def payments(self, request, pk=None):
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer

        order = self.get_object()
        payments = Payment.objects.filter(order=order).order_by("created_at")
        return Response(PaymentSerializer(payments, many=True).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        try:
            order = cancel_order(self.get_object(), request.user, request.data.get("reason", ""))
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="print")
    def print_order(self, request, pk=None):
        from apps.printers.services import register_print_job

        job = register_print_job(
            order=self.get_object(),
            user=request.user,
            job_type=request.data.get("job_type", "receipt"),
        )
        return Response({"print_job_id": str(job.id), "html": job.html_content})


class OrderItemViewSet(BaseTenantViewSet):
    serializer_class = OrderItemSerializer
    queryset = (
        OrderItem.objects.select_related("restaurant", "branch", "order__table", "order__command", "product", "batch")
        .prefetch_related("addons")
        .all()
    )
    filterset_fields = ["restaurant", "branch", "order", "production_sector", "status"]
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
