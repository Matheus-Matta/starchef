from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TenantModel
from apps.orders.models_consumption import ConsumptionItem, ProductionBatch


class Order(TenantModel):
    TYPE_TABLE = "table"
    TYPE_COMMAND = "command"
    TYPE_COUNTER = "counter"
    TYPE_DELIVERY = "delivery"
    TYPE_TAKEAWAY = "takeaway"
    TYPE_INTERNAL = "internal"

    TYPE_CHOICES = [
        (TYPE_COMMAND, "Command"),
        (TYPE_COUNTER, "Counter"),
        (TYPE_DELIVERY, "Delivery"),
        (TYPE_TAKEAWAY, "Takeaway"),
        (TYPE_INTERNAL, "Internal"),
    ]

    # Operational cycle (conta aberta)
    STATUS_OPEN = "open"
    STATUS_AWAITING_PAYMENT = "awaiting_payment"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUNDED = "refunded"
    # Pedido de trabalho cujos itens foram para um pedido consolidado. Ele
    # continua existindo como histórico (lotes de cozinha, tickets impressos,
    # snapshot de valor), mas NÃO fatura e não aceita mais escrita.

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_AWAITING_PAYMENT, "Awaiting payment"),
        (STATUS_PAID, "Paid"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    # Production cycle (cozinha) — independent of status
    PROD_IDLE = "idle"
    PROD_SENT = "sent_to_kitchen"
    PROD_PREPARING = "preparing"
    PROD_PARTIALLY_READY = "partially_ready"
    PROD_READY = "ready"
    PROD_DELIVERED = "delivered"

    PRODUCTION_STATUS_CHOICES = [
        (PROD_IDLE, "Idle"),
        (PROD_SENT, "Sent to kitchen"),
        (PROD_PREPARING, "Preparing"),
        (PROD_PARTIALLY_READY, "Partially ready"),
        (PROD_READY, "Ready"),
        (PROD_DELIVERED, "Delivered"),
    ]

    # Payment cycle — independent of status and production_status
    PAYMENT_PENDING = "pending"
    PAYMENT_PARTIAL = "partial"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_CANCELLED = "cancelled"

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PARTIAL, "Partial"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_REFUNDED, "Refunded"),
        (PAYMENT_CANCELLED, "Cancelled"),
    ]

    # Delivery cycle — só relevante para pedidos de entrega (módulo Entrega).
    DELIVERY_PENDING = "pending"
    DELIVERY_OUT = "out_for_delivery"
    DELIVERY_DELIVERED = "delivered"
    DELIVERY_FAILED = "failed"

    DELIVERY_STATUS_CHOICES = [
        (DELIVERY_PENDING, "Pending"),
        (DELIVERY_OUT, "Out for delivery"),
        (DELIVERY_DELIVERED, "Delivered"),
        (DELIVERY_FAILED, "Failed"),
    ]

    sequence = models.PositiveIntegerField()
    order_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    table = models.ForeignKey(
        "restaurants.Table",
        null=True,
        blank=True,
        related_name="orders",
        on_delete=models.SET_NULL,
    )
    command = models.ForeignKey(
        "restaurants.Command",
        null=True,
        blank=True,
        related_name="orders",
        on_delete=models.SET_NULL,
    )
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        related_name="orders",
        on_delete=models.SET_NULL,
    )
    delivery_address = models.ForeignKey(
        "customers.CustomerAddress",
        null=True,
        blank=True,
        related_name="delivery_orders",
        on_delete=models.SET_NULL,
    )
    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="orders_opened",
        on_delete=models.SET_NULL,
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="orders_closed",
        on_delete=models.SET_NULL,
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    production_status = models.CharField(
        max_length=32,
        choices=PRODUCTION_STATUS_CHOICES,
        default=PROD_IDLE,
        db_index=True,
    )
    opened_at = models.DateTimeField(auto_now_add=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_fee_enabled = models.BooleanField(default=True)
    # Percentual que originou `service_fee`, guardado no fechamento.
    #
    # A taxa e um valor em reais, mas ela e DERIVADA do subtotal. Sem guardar a
    # aliquota, um item que chegava depois do fechamento (a fila offline do PDV
    # entrega na ordem dela, e um item recusado por preco pode subir depois de
    # corrigido) aumentava o subtotal com a taxa congelada no subtotal antigo:
    # o total do servidor deixava de ser subtotal + 10%, e divergia do que o
    # PDV mostrou ao cliente. `None` significa "taxa fixada a mao" — um valor
    # que o gerente digitou nao pode ser reescrito por recalculo.
    service_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, default=None
    )
    fiscal_customer_cpf = models.CharField(max_length=11, blank=True, default="")
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_PENDING,
        db_index=True,
    )
    delivery_status = models.CharField(
        max_length=24,
        choices=DELIVERY_STATUS_CHOICES,
        default=DELIVERY_PENDING,
        db_index=True,
    )
    general_notes = models.TextField(blank=True)
    change_history = models.JSONField(default=list, blank=True)
    cancel_reason = models.TextField(blank=True)
    # Quem cancelou, quem liberou e como — o relatorio de cancelamentos lê
    # daqui; antes isso morava só no metadata do AuditLog.
    AUTHORIZATION_OWN = "own"
    AUTHORIZATION_CASH_PASSWORD = "cash_password"
    AUTHORIZATION_DELEGATED = "delegated"
    AUTHORIZATION_GRACE = "grace"
    AUTHORIZATION_CHOICES = [
        (AUTHORIZATION_OWN, "Própria"),
        (AUTHORIZATION_CASH_PASSWORD, "Senha do caixa"),
        (AUTHORIZATION_DELEGATED, "Usuário autorizado"),
        (AUTHORIZATION_GRACE, "Dentro da carência"),
    ]
    cancelled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="orders_cancelled", on_delete=models.SET_NULL
    )
    cancel_authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="orders_cancel_authorized", on_delete=models.SET_NULL
    )
    cancel_authorization = models.CharField(max_length=20, choices=AUTHORIZATION_CHOICES, blank=True, default="")

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "sequence"], name="unique_order_sequence_by_branch"),
        ]
        indexes = [
            models.Index(fields=["branch", "status", "opened_at"]),
            models.Index(fields=["branch", "payment_status"]),
            models.Index(fields=["restaurant", "opened_at"]),
            models.Index(fields=["restaurant", "updated_at"], name="orders_rest_updated_idx"),
        ]

    def __str__(self):
        return f"Order {self.sequence}"

    def save(self, *args, **kwargs):
        # Mantem a ultima atividade confiavel mesmo quando um chamador usa
        # update_fields e esquece o campo auto_now.
        self.updated_at = timezone.now()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = [*set(update_fields), "updated_at"]
        return super().save(*args, **kwargs)

    @property
    def is_locked(self):
        """Nada mais pode ser gravado neste pedido.

        `merged` entra aqui: os itens dele já estão no pedido consolidado, e
        aceitar lançamento, fechamento ou cancelamento na origem produziria
        uma venda que ninguém cobra — ou cobraria duas vezes.
        """
        return self.status in {
            self.STATUS_PAID,
            self.STATUS_CANCELLED,
            self.STATUS_REFUNDED,
        }


class OrderBatch(ProductionBatch):
    """A rodada de produção DE UM PEDIDO.

    O número, o serial, a carência e o estado vêm de `ProductionBatch`,
    compartilhado com a rodada da comanda.
    """

    order = models.ForeignKey(Order, related_name="batches", on_delete=models.CASCADE)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="batches_sent",
        on_delete=models.SET_NULL,
    )

    class Meta(ProductionBatch.Meta):
        constraints = [
            models.UniqueConstraint(fields=["order", "batch_number"], name="unique_batch_number_per_order"),
        ]

    def __str__(self):
        return f"Rodada #{self.batch_number} — Pedido {self.order_id}"


class OrderItem(ConsumptionItem):
    """O item DENTRO DE UM PEDIDO — o que vai ser cobrado.

    O que ele é, quanto custa e em que pé está na produção vem de
    `ConsumptionItem`, compartilhado com o item da comanda. Aqui fica só o que
    é do pedido: de qual pedido é, de qual comanda veio, e a rodada de cozinha.
    """

    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    # DE QUAL COMANDA este item veio. Nulo no balcão, na entrega e na retirada.
    #
    # Redundante com `command_item.command`, e de propósito: um pedido que paga
    # 200 comandas responde "quais cartões estão nesta conta" sem visitar 200
    # anotações, e o cupom por comanda é uma consulta só. A cópia nasce junto
    # com o item e nunca muda.
    #
    # `related_name="items"` devolve o HISTÓRICO INTEIRO do cartão, inclusive
    # almoços de semanas atrás. "O que a comanda tem AGORA" são os
    # `CommandItem` pendentes dela — nenhuma tela pode usar `command.items`
    # cru.
    command = models.ForeignKey(
        "restaurants.Command",
        null=True,
        blank=True,
        related_name="items",
        on_delete=models.PROTECT,
    )
    # DE QUAL ANOTAÇÃO DA COMANDA este item veio.
    #
    # O caixa inclui a comanda 13 no pedido: cada `CommandItem` pendente vira um
    # `OrderItem` aqui, e este campo é o fio entre os dois. É por ele que, ao
    # encerrar o pedido — pago, cancelado, estornado —, a anotação correspondente
    # é marcada como concluída e some da comanda.
    #
    # Nulo no item lançado direto no pedido (balcão, entrega, retirada), que
    # nunca passou por cartão nenhum.
    command_item = models.ForeignKey(
        "orders.CommandItem",
        null=True,
        blank=True,
        related_name="order_items",
        on_delete=models.PROTECT,
    )
    batch = models.ForeignKey(
        OrderBatch,
        null=True,
        blank=True,
        related_name="items",
        on_delete=models.SET_NULL,
    )
    product = models.ForeignKey("menu.Product", related_name="order_items", on_delete=models.PROTECT)
    # Coluna atual no quadro do KDS (Kanban). Nulo = ainda não posicionado
    # (o card aparece na coluna de entrada da estação). Ref. por string p/ evitar
    # ciclo de import entre orders <-> kitchen.
    kds_column = models.ForeignKey(
        "kitchen.KdsColumn",
        null=True,
        blank=True,
        related_name="order_items",
        on_delete=models.SET_NULL,
    )
    launched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="order_items_launched",
        on_delete=models.SET_NULL,
    )
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="order_items_voided", on_delete=models.SET_NULL
    )

    class Meta(ConsumptionItem.Meta):
        indexes = [
            models.Index(fields=["branch", "production_sector", "status"]),
            models.Index(fields=["order", "status"]),
        ]
        constraints = [
            # UMA anotação da comanda gera UM item de pedido.
            #
            # É a defesa de verdade contra dois caixas incluindo o mesmo cartão
            # em duas contas ao mesmo tempo: a conferência em Python só dá a
            # impressão de impedir, porque entre a leitura e a escrita cabe a
            # outra transação. Aqui o segundo perde, e o cliente não paga duas
            # vezes pelo mesmo prato.
            models.UniqueConstraint(
                fields=["command_item"],
                name="unique_order_item_per_command_item",
            ),
        ]


class OrderItemAddon(TenantModel):
    item = models.ForeignKey(OrderItem, related_name="addons", on_delete=models.CASCADE)
    addon = models.ForeignKey("menu.ProductAddon", related_name="order_item_addons", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.addon} ({self.item})"


# Os models da consolidação vivem em `models_merge.py` (arquivo próprio, como
# manda a organização do repositório). O import precisa ficar AQUI para o
# Django registrá-los junto da app.
from apps.orders.models_command_item import CommandBatch, CommandItem, CommandItemAddon  # noqa: E402,F401
