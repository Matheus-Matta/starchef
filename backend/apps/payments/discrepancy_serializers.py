"""Entrada e saída da divergência de vendas."""
from decimal import Decimal

from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer
from apps.payments.discrepancy import SalesDiscrepancy
from apps.payments.models import CashRegister, PaymentMethod
from apps.payments.terminals import operator_label


class _FormaSerializer(serializers.Serializer):
    payment_method = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.all_objects.all())
    # Duas casas e positivo: o DRF recusa "10.005" e "-3" com 400, sem
    # arredondar em silêncio (dinheiro nasce arredondado, não é corrigido).
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class SalesDiscrepancySerializer(TenantModelSerializer):
    by_payment_method = _FormaSerializer(many=True, write_only=True)
    payment_methods = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    cash_station_name = serializers.CharField(
        source="cash_register.cash_station.name", read_only=True, default=None
    )

    class Meta:
        model = SalesDiscrepancy
        fields = "__all__"
        read_only_fields = [
            "id", "created_at", "updated_at", "created_by", "updated_by", "amount",
            "restaurant", "branch", "status", "reviewed_by", "reviewed_at",
            "regularized_by", "regularized_at", "regularization_note",
            "cancelled_by", "cancelled_at", "cancel_reason",
        ]

    def get_payment_methods(self, obj):
        return obj.by_payment_method

    def get_created_by_name(self, obj):
        return operator_label(obj.created_by) if obj.created_by_id else ""

    def validate_reason(self, value):
        if not str(value or "").strip():
            raise serializers.ValidationError("Informe o motivo da divergência.")
        return value.strip()

    def validate_by_payment_method(self, formas):
        if not formas:
            raise serializers.ValidationError("Informe ao menos uma forma de pagamento.")
        account = getattr(self.context.get("request"), "account", None)
        vistas = set()
        for forma in formas:
            metodo = forma["payment_method"]
            if account is not None and metodo.account_id != account.pk:
                # Mesma resposta de "não existe": não revela forma de outra conta.
                raise serializers.ValidationError("Forma de pagamento não encontrada.")
            if metodo.pk in vistas:
                raise serializers.ValidationError(f"{metodo.name} aparece duas vezes.")
            vistas.add(metodo.pk)
        return formas

    def validate_cash_register(self, sessao):
        if sessao.status == CashRegister.STATUS_CANCELLED:
            raise serializers.ValidationError("Sessão de caixa cancelada não recebe divergência.")
        return sessao

    def validate(self, attrs):
        attrs = super().validate(attrs)
        formas = attrs.pop("by_payment_method", None)
        if formas is not None:
            attrs["by_payment_method"] = [
                {
                    "payment_method": str(f["payment_method"].pk),
                    "name": f["payment_method"].name,
                    "method_type": f["payment_method"].method_type,
                    "amount": str(f["amount"]),
                }
                for f in formas
            ]
            # Soma de valores já com duas casas: exata, sem arredondar de novo.
            attrs["amount"] = sum((f["amount"] for f in formas), Decimal("0.00"))
        sessao = attrs.get("cash_register") or getattr(self.instance, "cash_register", None)
        if sessao is not None:
            attrs["restaurant"] = sessao.restaurant
            attrs["branch"] = sessao.branch
        return attrs
