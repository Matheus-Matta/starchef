"""Promoções e cupons.

Dois assuntos, dois arquivos, um app. Ficam juntos porque compartilham o
vocabulário do desconto e porque quem cadastra um cadastra o outro na mesma
tarde — e separados em módulos porque promoção é preço de vitrine e cupom é
direito de uma pessoa: as regras não se parecem em nada.
"""

from apps.promotions.models.coupon import Coupon
from apps.promotions.models.discount_table import DiscountTable
from apps.promotions.models.promotion import Promotion
from apps.promotions.models.promotion_product import PromotionProduct
from apps.promotions.models.redemption import CouponRedemption

__all__ = [
    "Coupon",
    "CouponRedemption",
    "DiscountTable",
    "Promotion",
    "PromotionProduct",
]
