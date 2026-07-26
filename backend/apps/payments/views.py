from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.core.access import is_tenant_admin
from apps.core.modules import MODULE_FINANCEIRO
from apps.core.viewsets import BaseTenantViewSet, ReadOnlyTenantViewSet
from apps.payments.models import CashMovement, CashRegister, CashStation, Payment, PaymentMethod
from apps.payments.serializers import CashMovementSerializer, CashRegisterSerializer, CashStationSerializer, PaymentMethodSerializer, PaymentSerializer
from apps.payments.services import approve_cash_operation, close_cash_register, create_cash_movement, open_cash_register


class CashApprovalRateThrottle(UserRateThrottle):
    """Limita tentativas de senha sem reduzir o tráfego normal do PDV."""

    scope = "cash_approval"


class PaymentMethodViewSet(BaseTenantViewSet):
    serializer_class = PaymentMethodSerializer
    queryset = PaymentMethod.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["method_type", "is_active"]
    search_fields = ["name"]


class PaymentViewSet(ReadOnlyTenantViewSet):
    required_module = MODULE_FINANCEIRO  # historico analitico de pagamentos (o recebimento em si e do PDV/base)
    serializer_class = PaymentSerializer
    queryset = Payment.objects.select_related("restaurant", "branch", "order", "payment_method").all()
    filterset_fields = ["order", "payment_method", "status"]
    ordering_fields = ["paid_at", "amount"]


class CashStationViewSet(BaseTenantViewSet):
    serializer_class = CashStationSerializer
    queryset = CashStation.objects.select_related("restaurant").prefetch_related("operators", "sessions__opened_by").all()
    filterset_fields = ["is_active"]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code", "created_at"]

    def destroy(self, request, *args, **kwargs):
        station = self.get_object()
        if station.sessions.exclude(status__in=[
            CashRegister.STATUS_CLOSED,
            CashRegister.STATUS_CLOSED_DIFFERENCE,
            CashRegister.STATUS_CANCELLED,
        ]).exists():
            return Response(
                {"detail": "Feche o caixa antes de excluí-lo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class CashRegisterViewSet(BaseTenantViewSet):
    serializer_class = CashRegisterSerializer
    queryset = CashRegister.objects.select_related("restaurant", "branch", "opened_by", "closed_by").prefetch_related("movements").all()
    filterset_fields = ["status", "opened_by", "station"]
    ordering_fields = ["opened_at", "closed_at"]

    @action(detail=False, methods=["post"], url_path="open")
    def open(self, request):
        station = CashStation.objects.filter(
            pk=request.data.get("cash_station"),
            account=getattr(request, "account", None),
        ).select_related("restaurant").first()
        if station is None:
            return Response({"detail": "Selecione um caixa cadastrado no restaurante."}, status=status.HTTP_400_BAD_REQUEST)
        profile = getattr(request.user, "profile", None)
        if not is_tenant_admin(request.user) and getattr(profile, "restaurant_id", None) != station.restaurant_id:
            return Response({"detail": "O caixa selecionado não pertence ao seu restaurante."}, status=status.HTTP_403_FORBIDDEN)
        try:
            cash_register = open_cash_register(
                restaurant=station.restaurant,
                cash_station=station,
                user=request.user,
                opening_amount=request.data.get("opening_amount", 0),
                notes=request.data.get("notes", ""),
                station=request.data.get("station", "PDV principal"),
                device_identifier=request.data.get("device_identifier", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(cash_register).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        register = self.get_queryset().filter(opened_by=request.user).exclude(
            status__in=[CashRegister.STATUS_CLOSED, CashRegister.STATUS_CLOSED_DIFFERENCE, CashRegister.STATUS_CANCELLED]
        ).order_by("-opened_at").first()
        if register is None:
            return Response({"detail": "O operador não possui uma sessão de caixa em andamento."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(register).data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        try:
            cash_register = close_cash_register(
                cash_register=self.get_object(),
                user=request.user,
                actual_amount=request.data["actual_amount"],
                notes=request.data.get("notes", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(cash_register).data)

    @action(detail=True, methods=["post"], url_path="withdrawal")
    def withdrawal(self, request, pk=None):
        try:
            movement = create_cash_movement(
                cash_register=self.get_object(), user=request.user,
                movement_type=CashMovement.TYPE_WITHDRAWAL, amount=request.data.get("amount", 0),
                reason=request.data.get("reason", ""), destination=request.data.get("destination", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="supply")
    def supply(self, request, pk=None):
        try:
            movement = create_cash_movement(
                cash_register=self.get_object(), user=request.user,
                movement_type=CashMovement.TYPE_SUPPLY, amount=request.data.get("amount", 0),
                reason=request.data.get("reason", ""), destination=request.data.get("source", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["post"],
        url_path="approve",
        throttle_classes=[CashApprovalRateThrottle],
    )
    def approve(self, request, pk=None):
        movement = None
        if request.data.get("movement"):
            movement = CashMovement.objects.filter(pk=request.data["movement"], cash_register=self.get_object()).first()
        try:
            result = approve_cash_operation(
                cash_register=self.get_object(), user=request.user,
                reason=request.data.get("reason", ""), movement=movement,
                cash_password=request.data.get("cash_password") or None,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        serializer = CashMovementSerializer(result) if movement else self.get_serializer(result)
        return Response(serializer.data)

