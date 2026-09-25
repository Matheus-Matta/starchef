from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TenantModel

CENTAVOS = Decimal("0.01")


class Promotion(TenantModel):
    """Uma regra de desconto dentro de uma tabela.

    O ALVO É UM SÓ POR REGRA — produtos, ou categorias, ou setores. Misturar
    alvos na mesma regra criava a pergunta sem resposta: se o produto está na
    lista E a categoria dele também, qual desconto vale? Uma regra por alvo faz
    a prioridade ser legível na tela, de cima para baixo.

    A POSIÇÃO É A PRIORIDADE dentro da tabela: quem está no topo ganha. É o
    único critério que o gerente consegue conferir de relance — ordenar por
    "maior desconto" ou "mais específico" exigiria simular a regra para saber
    quem venceu.
    """

    TARGET_PRODUCTS = "products"
    TARGET_CATEGORIES = "categories"
    TARGET_SECTORS = "sectors"
    TARGET_ALL = "all"
    TARGET_CHOICES = [
        (TARGET_PRODUCTS, "Produtos escolhidos"),
        (TARGET_CATEGORIES, "Categorias"),
        (TARGET_SECTORS, "Setores"),
        (TARGET_ALL, "Todo o cardápio"),
    ]

    KIND_PERCENT = "percent"
    KIND_AMOUNT = "amount"
    KIND_FIXED = "fixed"
    KIND_CHOICES = [
        (KIND_PERCENT, "Percentual sobre o preço"),
        (KIND_AMOUNT, "Valor em reais abatido"),
        (KIND_FIXED, "Preço fixo"),
    ]

    # O ESCOPO DE LOJA É DA TABELA, não da regra. A regra carrega o campo por
    # herança do `TenantModel`, mas ele é opcional aqui: preenchido, seria uma
    # segunda verdade sobre em qual loja a regra vale — e as duas divergiriam na
    # primeira vez que alguém mudasse o escopo da tabela.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )
    table = models.ForeignKey(
        "promotions.DiscountTable",
        related_name="rules",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=140)
    # O topo ganha. Começa em 1 para a conversa com o operador ("a regra 1")
    # bater com o que ele vê.
    position = models.PositiveIntegerField(default=1, db_index=True)
    target_type = models.CharField(max_length=16, choices=TARGET_CHOICES, default=TARGET_PRODUCTS)
    discount_kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=KIND_PERCENT)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_enabled = models.BooleanField(default=True, db_index=True)
    # Janela própria, DENTRO da janela da tabela. Serve para "só no primeiro
    # fim de semana da tabela do mês"; vazia, herda a tabela.
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    products = models.ManyToManyField(
        "menu.Product",
        through="promotions.PromotionProduct",
        related_name="promotions",
        blank=True,
    )
    categories = models.ManyToManyField(
        "menu.ProductCategory",
        related_name="promotions",
        blank=True,
    )
    sectors = models.ManyToManyField(
        "restaurants.TableSector",
        related_name="promotions",
        blank=True,
    )

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["table", "position"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_promotion_position_per_table",
            ),
        ]
        indexes = [models.Index(fields=["table", "is_enabled"])]

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        """A tabela manda, mas a regra pode se calar antes dela."""
        if not self.is_enabled or self.deleted_at is not None:
            return False
        if not self.table.is_active:
            return False
        agora = timezone.now()
        if self.starts_at and agora < self.starts_at:
            return False
        if self.ends_at and agora > self.ends_at:
            return False
        return True

    def preco_para(self, base, override=None):
        """O preço que esta regra cobra por um item cujo preço cheio é `base`.

        `override` é o vínculo com o produto quando a regra aponta produtos
        direto (`PromotionProduct`): ele pode carregar o "por" digitado à mão,
        que vence o tipo de desconto da regra. É como uma promoção de encarte
        realmente se escreve — "de 30 por 15" — e não como uma conta de
        percentual que por acaso chega perto.

        Nunca devolve negativo: 120% de desconto é erro de digitação, e um item
        de preço negativo devolve dinheiro no fechamento do caixa.
        """
        base = Decimal(base or 0)
        se_digitado = getattr(override, "promotional_price", None)
        if se_digitado is not None:
            return self._centavos(se_digitado)
        if self.discount_kind == self.KIND_FIXED:
            return self._centavos(self.discount_value)
        if self.discount_kind == self.KIND_AMOUNT:
            return self._centavos(base - self.discount_value)
        fator = (Decimal(100) - Decimal(self.discount_value)) / Decimal(100)
        return self._centavos(base * fator)

    @staticmethod
    def _centavos(valor):
        valor = Decimal(valor or 0).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        return valor if valor > 0 else Decimal("0.00")
