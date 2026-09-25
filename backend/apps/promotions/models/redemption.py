from django.db import models

from apps.core.models import TenantModel
from apps.promotions.models.coupon import Coupon


class CouponRedemption(TenantModel):
    """O resgate: a prova de que este cupom foi usado neste pedido.

    É uma tabela própria, e não um contador no cupom, porque "compra única por
    cliente" é uma pergunta sobre QUEM usou — um número não responde. E porque
    o cancelamento do pedido precisa devolver o direito: apagar o resgate
    devolve; decrementar um contador perde a conta na primeira condição de
    corrida.
    """

    coupon = models.ForeignKey(Coupon, related_name="redemptions", on_delete=models.CASCADE)
    order = models.ForeignKey("orders.Order", related_name="coupon_redemptions", on_delete=models.CASCADE)
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        related_name="coupon_redemptions",
        on_delete=models.SET_NULL,
    )
    # O CPF fica GRAVADO aqui, e não só no cliente: o cupom de "um por CPF"
    # precisa barrar o mesmo CPF mesmo quando ele volta como outro cadastro.
    document = models.CharField(max_length=20, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["coupon", "order"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_coupon_redemption_per_order",
            ),
        ]
        indexes = [
            models.Index(fields=["coupon", "customer"]),
            models.Index(fields=["coupon", "document"]),
        ]

    def __str__(self):
        return f"{self.coupon_id} · {self.order_id}"
