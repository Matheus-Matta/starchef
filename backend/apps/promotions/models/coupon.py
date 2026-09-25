from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TenantModel

CENTAVOS = Decimal("0.01")


class Coupon(TenantModel):
    """O cupom de desconto: um código que o cliente diz e o caixa digita.

    É diferente de promoção por natureza, e não por grau. Promoção muda o preço
    da vitrine para todo mundo, sem ninguém pedir; cupom é um direito de UMA
    pessoa, que precisa ser reconhecida e contada. Por isso aqui existe
    resgate, limite e CPF — e na promoção, não.

    O VALOR MÍNIMO NÃO CONTA TAXA DE SERVIÇO NEM ENTREGA. Contar as taxas faria
    o cupom de "pedidos acima de R$ 50" liberar num pedido de R$ 44 de comida
    que chegou a 50 por causa do frete — o restaurante daria desconto sobre uma
    venda que nunca atingiu o patamar que ele quis premiar.
    """

    KIND_PERCENT = "percent"
    KIND_AMOUNT = "amount"
    KIND_FREE_DELIVERY = "free_delivery"
    KIND_CHOICES = [
        (KIND_PERCENT, "Percentual sobre o subtotal"),
        (KIND_AMOUNT, "Valor em reais"),
        (KIND_FREE_DELIVERY, "Entrega grátis"),
    ]

    # Compartilhado entre restaurantes: vazio = a conta inteira, preenchido =
    # só aquela loja. Sobrescreve o FK obrigatório do `TenantModel` — mesmo
    # padrão de `menu.ProductCategory` e `invoices.FiscalProfile`.
    #
    # Sem o opcional, uma rede de dez lojas cadastraria o MESMO cupom dez
    # vezes, e a décima primeira loja abriria sem cupom nenhum.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )
    code = models.CharField(
        max_length=40,
        db_index=True,
        help_text="O que o cliente informa. Guardado em MAIÚSCULAS.",
    )
    name = models.CharField(max_length=140, blank=True)
    description = models.CharField(max_length=255, blank=True)
    discount_kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_PERCENT)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Teto do percentual. "20% de desconto" sem teto num pedido de mil reais
    # são duzentos reais que ninguém aprovou.
    max_discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Teto em reais para o desconto percentual. Vazio = sem teto.",
    )
    minimum_order_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Mínimo em produtos, SEM taxa de serviço e SEM entrega.",
    )

    is_enabled = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    # Zero é sem limite em todos estes: é o valor que um campo numérico em
    # branco assume, e "em branco" para quem cadastra significa "não limita".
    usage_limit = models.PositiveIntegerField(
        default=0,
        help_text="Total de usos do cupom. 0 = ilimitado.",
    )
    usage_limit_per_customer = models.PositiveIntegerField(
        default=0,
        help_text="Usos por cliente. 0 = ilimitado.",
    )
    single_use_per_customer = models.BooleanField(
        default=False,
        help_text="Compra única por cliente (equivale a 1 uso por cliente).",
    )
    first_purchase_only = models.BooleanField(
        default=False,
        help_text="Só vale para quem ainda não tem pedido pago.",
    )
    requires_document = models.BooleanField(
        default=False,
        help_text="Exige CPF no pedido para liberar o cupom.",
    )
    # O CPF É A IDENTIDADE. Quem tem direito ao cupom se descobre pelo CPF
    # do pedido (o mesmo que vai na nota), e não por um "cliente selecionado"
    # à parte: no caixa, o que a pessoa informa é o CPF. Cupom restrito a
    # grupo ou a cliente exige CPF por consequência, sem precisar marcar
    # nada — sem ele não existe a quem comparar.
    #
    # Vazios = vale para todo mundo, que é o padrão certo: um cupom nasce
    # público, e quem quer restringir escolhe a quem.
    customer_groups = models.ManyToManyField(
        "customers.CustomerGroup",
        related_name="coupons",
        blank=True,
        help_text="Vazio = todos os grupos.",
    )
    customers = models.ManyToManyField(
        "customers.Customer",
        related_name="coupons",
        blank=True,
        help_text="Vazio = todos os clientes.",
    )
    order_types = models.JSONField(
        default=list,
        blank=True,
        help_text="Tipos de pedido aceitos (lista). Vazio = todos.",
    )
    combines_with_promotions = models.BooleanField(
        default=True,
        help_text="Desligado, o cupom é recusado em pedido que já tem item em promoção.",
    )

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "code"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_coupon_code_per_account",
            ),
        ]
        indexes = [models.Index(fields=["account", "is_enabled"])]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        # A normalização é no model, e não no serializer: o cupom também entra
        # por importação e por sincronização, e "natal10" digitado no caixa tem
        # de achar o "NATAL10" cadastrado pelo escritório.
        self.code = (self.code or "").strip().upper()
        return super().save(*args, **kwargs)

    @property
    def is_active(self):
        if not self.is_enabled or self.deleted_at is not None:
            return False
        agora = timezone.now()
        if self.starts_at and agora < self.starts_at:
            return False
        if self.ends_at and agora > self.ends_at:
            return False
        return True

    @property
    def limite_por_cliente(self):
        """`single_use_per_customer` é o mesmo que um uso — sem dois números."""
        if self.single_use_per_customer:
            return 1
        return self.usage_limit_per_customer or 0

    def desconto_para(self, subtotal, delivery_fee=Decimal("0.00")):
        """Quanto este cupom abate, dado o subtotal de produtos e o frete.

        Nunca devolve mais do que a base que ele desconta: um cupom de R$ 50
        num pedido de R$ 30 abate 30, e não devolve 20 de troco.
        """
        subtotal = Decimal(subtotal or 0)
        if self.discount_kind == self.KIND_FREE_DELIVERY:
            # A entrega grátis abate o FRETE, não o subtotal: num pedido de
            # balcão (frete zero) ela não vale nada, e é essa a verdade.
            return self._centavos(delivery_fee)
        if self.discount_kind == self.KIND_AMOUNT:
            return self._centavos(min(self.discount_value, subtotal))
        bruto = subtotal * Decimal(self.discount_value) / Decimal(100)
        if self.max_discount_amount is not None:
            bruto = min(bruto, Decimal(self.max_discount_amount))
        return self._centavos(min(bruto, subtotal))

    @staticmethod
    def _centavos(valor):
        valor = Decimal(valor or 0).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        return valor if valor > 0 else Decimal("0.00")
