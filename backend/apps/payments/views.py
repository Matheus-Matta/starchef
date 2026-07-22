from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.modules import MODULE_FINANCEIRO
from apps.core.viewsets import BaseTenantViewSet, ReadOnlyTenantViewSet
from apps.payments.models import CashRegister, Payment, PaymentMethod
from apps.payments.serializers import CashRegisterSerializer, PaymentMethodSerializer, PaymentSerializer
from apps.payments.services import close_cash_register, open_cash_register


class PaymentMethodViewSet(BaseTenantViewSet):
    serializer_class = PaymentMethodSerializer
    queryset = PaymentMethod.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["restaurant", "branch", "method_type", "is_active"]
    search_fields = ["name"]


class PaymentViewSet(ReadOnlyTenantViewSet):
    required_module = MODULE_FINANCEIRO  # historico analitico de pagamentos (o recebimento em si e do PDV/base)
    serializer_class = PaymentSerializer
    queryset = Payment.objects.select_related("restaurant", "branch", "order", "payment_method").all()
    filterset_fields = ["restaurant", "branch", "order", "payment_method", "status"]
    ordering_fields = ["paid_at", "amount"]


class CashRegisterViewSet(BaseTenantViewSet):
    serializer_class = CashRegisterSerializer
    queryset = CashRegister.objects.select_related("restaurant", "branch", "opened_by", "closed_by").prefetch_related("movements").all()
    filterset_fields = ["restaurant", "branch", "status"]
    ordering_fields = ["opened_at", "closed_at"]

    @action(detail=False, methods=["post"], url_path="open")
    def open(self, request):
        profile = getattr(request.user, "profile", None)
        try:
            cash_register = open_cash_register(
                branch=profile.branch,
                user=request.user,
                opening_amount=request.data.get("opening_amount", 0),
                notes=request.data.get("notes", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(cash_register).data, status=status.HTTP_201_CREATED)

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

