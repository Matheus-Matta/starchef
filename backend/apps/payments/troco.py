"""Quem pode dar troco: o dinheiro sempre; as outras formas, se o restaurante deixar.

O troco de cartão, PIX ou voucher sai da gaveta sem que dinheiro nenhum tenha
entrado nela — a maquininha cobrou R$ 100 numa conta de R$ 50 e o cliente leva
R$ 50 em espécie. É legítimo, mas é a saída de caixa mais fácil de errar e de
se perder: foi um troco assim que deixou a nuvem R$ 50 acima da loja.
`Restaurant.allow_change_on_non_cash` desligado faz essas formas pararem no
restante. 400, e não 409: é o valor digitado que está errado, não o estado.
"""
from rest_framework.exceptions import ValidationError


def conferir_troco(*, restaurant, payment_method, change_amount, remaining):
    from apps.payments.models import PaymentMethod

    if change_amount <= 0 or payment_method.method_type == PaymentMethod.TYPE_CASH:
        return
    if getattr(restaurant, "allow_change_on_non_cash", True):
        return
    raise ValidationError(
        f"Este restaurante dá troco só em dinheiro: em {payment_method.name}, "
        f"receba no máximo R$ {remaining:.2f}."
    )
