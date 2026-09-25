from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.orders.models import Order
from apps.promotions.models import Coupon, CouponRedemption

TIPOS_DE_PEDIDO = {valor for valor, _ in Order.TYPE_CHOICES}


class CouponSerializer(TenantModelSerializer):
    """O cadastro do cupom.

    `usage_count` e `remaining_uses` saem na listagem porque a pergunta que quem
    administra faz não é "o cupom existe?", é "quanto dele ainda sobra?" — e sem
    o número ela só se responde abrindo os pedidos.
    """

    is_active = serializers.BooleanField(read_only=True)
    usage_count = serializers.SerializerMethodField()
    remaining_uses = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_usage_count(self, obj):
        anotado = getattr(obj, "total_resgates", None)
        if anotado is not None:
            return anotado
        return obj.redemptions.count()

    def get_remaining_uses(self, obj):
        if not obj.usage_limit:
            return None
        return max(obj.usage_limit - self.get_usage_count(obj), 0)

    def validate_code(self, value):
        codigo = (value or "").strip().upper()
        if not codigo:
            raise serializers.ValidationError("Informe o código do cupom.")
        if " " in codigo:
            # Espaço no meio é o que faz o cliente ditar errado no telefone e o
            # caixa digitar diferente do cadastrado.
            raise serializers.ValidationError("O código não pode ter espaços.")
        return codigo

    def validate_order_types(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("Informe uma lista de tipos de pedido.")
        invalidos = [item for item in value if item not in TIPOS_DE_PEDIDO]
        if invalidos:
            aceitos = ", ".join(sorted(TIPOS_DE_PEDIDO))
            raise serializers.ValidationError(f"Tipo de pedido desconhecido: {', '.join(invalidos)}. Aceitos: {aceitos}.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self._conferir_janela(attrs)
        self._conferir_desconto(attrs)
        return attrs

    def _conferir_janela(self, attrs):
        inicio = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        fim = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if inicio and fim and fim <= inicio:
            raise serializers.ValidationError({"ends_at": "O fim da validade tem de ser depois do início."})

    def _conferir_desconto(self, attrs):
        def atual(campo, padrao=None):
            return attrs.get(campo, getattr(self.instance, campo, padrao))

        tipo = atual("discount_kind", Coupon.KIND_PERCENT)
        valor = atual("discount_value", 0)
        if tipo == Coupon.KIND_PERCENT:
            if valor > 100:
                raise serializers.ValidationError({"discount_value": "Um desconto percentual não passa de 100%."})
            if not valor:
                raise serializers.ValidationError({"discount_value": "Informe o percentual do desconto."})
        elif tipo == Coupon.KIND_AMOUNT and not valor:
            raise serializers.ValidationError({"discount_value": "Informe o valor em reais do desconto."})
        # `max_discount_amount` só faz sentido no percentual: num cupom de
        # R$ 10 o teto seria um segundo valor dizendo a mesma coisa, e os dois
        # divergiriam na primeira edição.
        if tipo != Coupon.KIND_PERCENT and atual("max_discount_amount") is not None:
            raise serializers.ValidationError(
                {"max_discount_amount": "O teto só se aplica a desconto percentual."}
            )


class CouponRedemptionSerializer(TenantModelSerializer):
    """O resgate, só leitura. Ele nasce do pagamento, nunca de um POST."""

    coupon_code = serializers.CharField(source="coupon.code", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    order_sequence = serializers.IntegerField(source="order.sequence", read_only=True)

    class Meta:
        model = CouponRedemption
        fields = [
            "id",
            "coupon",
            "coupon_code",
            "order",
            "order_sequence",
            "customer",
            "customer_name",
            "document",
            "amount",
            "created_at",
        ]
        read_only_fields = fields
