from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from apps.payments.models import CashMovement, CashRegister, Payment, PaymentMethod


class PaymentMethodSerializer(TenantModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class PaymentSerializer(TenantModelSerializer):
    payment_method_name = serializers.CharField(source="payment_method.name", read_only=True)

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by", "paid_at", "status"]


class CashMovementSerializer(TenantModelSerializer):
    class Meta:
        model = CashMovement
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class CashRegisterSerializer(TenantModelSerializer):
    movements = CashMovementSerializer(many=True, read_only=True)

    class Meta:
        model = CashRegister
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "opened_at",
            "closed_at",
            "expected_amount",
            "difference_amount",
        ]

