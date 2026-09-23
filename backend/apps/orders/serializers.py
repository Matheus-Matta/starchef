from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.orders.models import Order, OrderBatch, OrderItem, OrderItemAddon


class OrderItemAddonSerializer(TenantModelSerializer):
    addon_name = serializers.CharField(source="addon.name", read_only=True)

    class Meta:
        model = OrderItemAddon
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "total_price"]


class OrderItemSerializer(TenantModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    pricing_unit = serializers.CharField(source="product.pricing_unit", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    # Fields for KDS display
    order_sequence = serializers.IntegerField(source="order.sequence", read_only=True)
    order_type = serializers.CharField(source="order.order_type", read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)
    order_payment_status = serializers.CharField(source="order.payment_status", read_only=True)
    order_production_status = serializers.CharField(source="order.production_status", read_only=True)
    order_delivery_status = serializers.CharField(source="order.delivery_status", read_only=True)
    kds_position = serializers.SerializerMethodField()
    kds_entered_at = serializers.SerializerMethodField()
    order_table_number = serializers.SerializerMethodField()
    order_command_code = serializers.SerializerMethodField()
    command_number = serializers.IntegerField(source="command.number", read_only=True, default=None)
    command_code = serializers.CharField(source="command.code", read_only=True, default=None)
    batch_number = serializers.IntegerField(source="batch.batch_number", read_only=True, default=None)
    addons = OrderItemAddonSerializer(many=True, read_only=True)

    class Meta:
        model = OrderItem
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "total_price",
            "sent_to_kitchen_at",
            "preparation_started_at",
            "ready_at",
            "delivered_at",
            # `fields = "__all__"` torna GRAVÁVEL todo campo novo que não
            # apareça aqui. Estes quatro só mudam dentro dos serviços
            # transacionais: um PATCH que reescrevesse a comanda de um item
            # mudaria de quem é o prato, e um que reabrisse `command_status`
            # devolveria à comanda um item já pago.
            "command",
            "command_status",
            "command_closed_at",
        ]

    def get_order_table_number(self, obj):
        """A mesa da PRODUÇÃO, não a do pedido atual.

        O pedido guarda a mesa como histórico; quem responde "onde este prato
        vai" é o próprio item, que carrega a comanda desde o lançamento.
        """
        try:
            order = obj.order
            return order.table.number if order.table_id else None
        except Exception:
            return None

    def get_order_command_code(self, obj):
        """A comanda do ITEM, com o pedido só como reserva histórica."""
        try:
            if obj.command_id:
                return obj.command.code
            order = obj.order
            return order.command.code if order.command_id else None
        except Exception:
            return None

    def _station_position(self, obj):
        station_id = self.context.get("kds_station_id")
        if not station_id:
            return None
        return next(
            (position for position in obj.kds_positions.all() if str(position.station_id) == str(station_id)),
            None,
        )

    def get_kds_position(self, obj):
        position = self._station_position(obj)
        return str(position.column_id) if position else None

    def get_kds_entered_at(self, obj):
        position = self._station_position(obj)
        return position.entered_at if position else None


class OrderBatchSerializer(TenantModelSerializer):
    sent_by_name = serializers.CharField(source="sent_by.get_full_name", read_only=True, default=None)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = OrderBatch
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "batch_number", "sent_at"]


class OrderSerializer(TenantModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    # OS RECEBIMENTOS VIAJAM COM O PEDIDO.
    #
    # `payments` e uma relacao reversa: `fields = "__all__"` nao a inclui. O
    # PDV grava o recebimento local-first e, quando a fila entrega, aplica por
    # cima a versao do servidor — que vinha SEM pagamento nenhum. O pedido
    # ficava sem recebimento no armazenamento local no instante seguinte a
    # sincronizacao, e era desse retrato que a emissao fiscal era montada: o
    # PDV recusava a propria venda com "A venda nao tem recebimento
    # registrado" e a NFC-e nunca era emitida.
    #
    # Tambem e o que faz um pedido pago reaberto mostrar como foi pago: a tela
    # de pagamento le a lista pelo mesmo caminho.
    payments = serializers.SerializerMethodField()
    fiscal = serializers.SerializerMethodField()
    def get_payments(self, obj):
        """Recebimentos aprovados do pedido, na ordem em que entraram.

        So os aprovados: um recebimento cancelado nao compoe o valor pago nem
        entra na NFC-e.
        """
        from apps.payments.serializers import PaymentSerializer

        payments = [
            payment
            for payment in obj.payments.all()
            if payment.status == "approved"
        ]
        payments.sort(key=lambda payment: payment.created_at)
        return PaymentSerializer(payments, many=True, context=self.context).data

    table_number = serializers.CharField(source="table.number", read_only=True, default=None)
    command_number = serializers.IntegerField(source="command.number", read_only=True, default=None)
    command_code = serializers.CharField(source="command.code", read_only=True, default=None)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    customer_document = serializers.CharField(source="customer.document", read_only=True, default=None)

    def get_fiscal(self, obj):
        """Situacao da NFC-e deste pedido, ou `None` quando ainda nao ha nota.

        E o que permite a tela oferecer a acao certa — emitir quando nao ha
        documento, imprimir quando ja existe um autorizado — em vez de um
        botao unico que so revela o que faz depois do clique.

        `Order.invoice` e OneToOne; o queryset da view usa `select_related`
        para isto nao virar uma consulta por linha na listagem.
        """
        from apps.invoices.services import fiscal_state_of, is_fiscally_printable

        invoice = getattr(obj, "invoice", None)
        if invoice is None:
            return None
        return {
            "id": str(invoice.id),
            "status": invoice.status,
            "fiscal_state": fiscal_state_of(invoice),
            "printable": is_fiscally_printable(invoice),
            "number": invoice.number,
            "error_message": invoice.error_message,
        }

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = [
            "id",
            "sequence",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "opened_at",
            "closed_at",
            "subtotal",
            "service_fee",
            "service_fee_enabled",
            "service_fee_percent",
            "fiscal_customer_cpf",
            "total",
            "payment_status",
            "production_status",
            "change_history",
        ]

    def validate_order_type(self, value):
        if value == Order.TYPE_TABLE:
            raise serializers.ValidationError(
                "Pedidos de salão devem ser abertos por uma comanda e depois vinculados à mesa."
            )
        return value


from apps.orders.serializers_command_item import CommandItemSerializer  # noqa: E402,F401
