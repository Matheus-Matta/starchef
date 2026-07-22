from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.payments.models import CashMovement, CashRegister, Payment, PaymentMethod


class PaymentMethodSerializer(TenantModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class PaymentSerializer(TenantModelSerializer):
    payment_method_name = serializers.CharField(source="payment_method.name", read_only=True)
    payment_method_type = serializers.CharField(source="payment_method.method_type", read_only=True)

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "paid_at", "status"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Subtipo débito/crédito é obrigatório para cartão e proibido nos demais
        # métodos (STC-061). O tipo vem do próprio método de pagamento escolhido.
        method = attrs.get("payment_method") or getattr(self.instance, "payment_method", None)
        subtype = attrs.get("card_subtype", getattr(self.instance, "card_subtype", ""))
        if method and method.method_type == PaymentMethod.TYPE_CARD:
            if not subtype:
                raise serializers.ValidationError({"card_subtype": "Selecione débito ou crédito para pagamento com cartão."})
        elif subtype:
            raise serializers.ValidationError({"card_subtype": "Subtipo só se aplica a pagamento com cartão."})
        return attrs


class CashMovementSerializer(TenantModelSerializer):
    class Meta:
        model = CashMovement
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


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

