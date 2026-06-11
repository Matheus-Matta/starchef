from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin
from apps.menu.models import Product
from apps.orders.models import Order, OrderItem
from apps.orders.serializers import OrderItemSerializer, OrderSerializer
from apps.orders.services import (
    add_order_item,
    cancel_order,
    close_order,
    create_order,
    send_order_to_kitchen,
    update_order_item_status,
)


class OrderViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    queryset = (
        Order.objects.select_related("restaurant", "branch", "table", "command", "customer", "delivery_address")
        .prefetch_related("items__product", "items__addons")
        .all()
    )
    filterset_fields = ["restaurant", "branch", "order_type", "status", "payment_status", "table", "customer"]
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

        product = Product.objects.get(pk=request.data["product"])
        item = add_order_item(
            order=order,
            product=product,
            quantity=request.data.get("quantity", 1),
            user=request.user,
            variations=request.data.get("variations", []),
            customer_note=request.data.get("customer_note", ""),
        )
        return Response(OrderItemSerializer(item).data, status=status.HTTP_201_CREATED)

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


class OrderItemViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = OrderItemSerializer
    queryset = OrderItem.objects.select_related("restaurant", "branch", "order", "product").prefetch_related("addons").all()
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

