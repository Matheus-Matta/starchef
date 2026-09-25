"""O resgate do cupom: a prova de que ele foi usado.

Separado de `coupon_service` porque o RITMO é outro. Aplicar cupom é coisa de
conta aberta, que muda a cada item; o resgate acontece uma vez, no pagamento, e
só volta atrás no cancelamento.

O resgate SÓ NASCE NO PAGAMENTO. Gravado na aplicação, um cupom de compra única
queimaria num pedido abandonado e o cliente perderia o direito sem ter comprado
nada.
"""

from decimal import Decimal

from django.db import transaction

from apps.promotions.coupon_identity import cliente_por_cpf, cpf_do_pedido
from apps.promotions.models import CouponRedemption


@transaction.atomic
def registrar_resgate(order):
    """Grava o resgate do cupom deste pedido — no pagamento, e uma vez só.

    Idempotente de propósito: o pagamento pode ser confirmado duas vezes (fila
    offline reenviando, webhook repetido), e um segundo resgate faria o cupom de
    compra única aparecer como usado duas vezes pela mesma pessoa.
    """
    if not order.coupon_id or Decimal(order.coupon_discount or 0) <= 0:
        return None
    existente = CouponRedemption.all_objects.filter(
        coupon_id=order.coupon_id,
        order_id=order.pk,
        deleted_at__isnull=True,
    ).first()
    if existente is not None:
        return existente
    cpf = cpf_do_pedido(order)
    cliente = order.customer or cliente_por_cpf(order.account_id, cpf)
    return CouponRedemption.objects.create(
        account_id=order.account_id,
        restaurant_id=order.restaurant_id,
        branch_id=order.branch_id,
        coupon_id=order.coupon_id,
        order_id=order.pk,
        customer=cliente,
        document=cpf,
        amount=Decimal(order.coupon_discount or 0),
    )


@transaction.atomic
def devolver_resgate(order):
    """Devolve o direito quando o pedido é cancelado ou estornado.

    Apaga o resgate em vez de decrementar um contador: contador perde a conta na
    primeira condição de corrida, e "quem usou" deixa de ser respondível.
    """
    return CouponRedemption.all_objects.filter(order_id=order.pk).delete()
