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

from apps.core.api_errors import CouponRejected
from apps.promotions.coupon_identity import (
    cliente_por_cpf,
    cpf_do_pedido,
    usos_da_pessoa,
    usos_do_cupom,
)
from apps.promotions.models import Coupon, CouponRedemption


@transaction.atomic
def registrar_resgate(order):
    """Grava o resgate do cupom deste pedido — no pagamento, e uma vez só.

    Idempotente de propósito: o pagamento pode ser confirmado duas vezes (fila
    offline reenviando, webhook repetido), e um segundo resgate faria o cupom de
    compra única aparecer como usado duas vezes pela mesma pessoa.

    O LIMITE É RECONFERIDO AQUI, COM O CUPOM TRAVADO, e não é zelo: entre a
    aplicação (no fechamento) e o pagamento existe uma janela, e duas vendas
    simultâneas com o mesmo cupom atravessavam as duas a conferência do
    fechamento. O teste de carga mediu isso: seis vendas levaram um cupom de uso
    único. `select_for_update` no cupom serializa os resgates concorrentes — quem
    chega depois vê o uso de quem chegou antes.

    Quando o limite esgotou nessa janela, RECUSA. Parece durão, e é o oposto:
    nada de dinheiro se moveu ainda (o recebimento está sendo gravado nesta mesma
    transação, e a recusa a desfaz), e o caixa retira o cupom e cobra o valor
    cheio. Deixar passar seria dar o desconto e descobrir no fechamento do mês.
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
    # A TRAVA É NO CUPOM, e não no pedido: o que dois caixas disputam é o ÚLTIMO
    # USO do mesmo cupom, e cada um está no seu próprio pedido.
    cupom = Coupon.all_objects.select_for_update().get(pk=order.coupon_id)
    cpf = cpf_do_pedido(order)
    cliente = order.customer or cliente_por_cpf(order.account_id, cpf)
    _recusar_se_esgotou(cupom, cpf, cliente)
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


def _recusar_se_esgotou(cupom, cpf, cliente):
    """As duas contagens que a corrida invalida, conferidas sob a trava."""
    if cupom.usage_limit and usos_do_cupom(cupom) >= cupom.usage_limit:
        raise CouponRejected(
            f'O cupom "{cupom.code}" esgotou o limite de usos enquanto esta venda era '
            "fechada. Retire o cupom e cobre o valor cheio."
        )
    limite = cupom.limite_por_cliente
    if limite and usos_da_pessoa(cupom, cpf, cliente) >= limite:
        raise CouponRejected(
            f'O cupom "{cupom.code}" já foi usado por este cliente enquanto esta venda '
            "era fechada. Retire o cupom e cobre o valor cheio."
        )


@transaction.atomic
def devolver_resgate(order):
    """Devolve o direito quando o pedido é cancelado ou estornado.

    Apaga o resgate em vez de decrementar um contador: contador perde a conta na
    primeira condição de corrida, e "quem usou" deixa de ser respondível.
    """
    return CouponRedemption.all_objects.filter(order_id=order.pk).delete()
