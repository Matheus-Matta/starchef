from django.db import models

from apps.core.models import TenantModel
from apps.promotions.models.promotion import Promotion


class PromotionProduct(TenantModel):
    """O vínculo regra ↔ produto, com o "de/por" próprio do encarte.

    É um model, e não um M2M simples, porque a promoção de produto precisa
    dizer DOIS números que o cadastro não tem: o "por" que será cobrado e o
    "de" que será exibido riscado.

    O "DE" PODE SER MAIOR QUE O PREÇO CADASTRADO, e é de propósito: o produto
    custa 20, o encarte anuncia "de 30 por 15". Guardar isso no cadastro
    obrigaria a subir o preço real do produto para 30 — e quem comprasse fora
    da promoção pagaria 30 de verdade.
    """

    # O ESCOPO DE LOJA É DA TABELA, não do vínculo. O vínculo carrega o campo por
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
    promotion = models.ForeignKey(Promotion, related_name="product_links", on_delete=models.CASCADE)
    product = models.ForeignKey("menu.Product", related_name="promotion_links", on_delete=models.CASCADE)
    promotional_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='O "por". Vazio, aplica o desconto da regra sobre o preço cadastrado.',
    )
    compare_at_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='O "de" exibido riscado. Vazio, exibe o preço cadastrado.',
    )

    class Meta:
        ordering = ["product__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["promotion", "product"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_product_per_promotion",
            ),
        ]

    def __str__(self):
        return f"{self.promotion_id} · {self.product_id}"
