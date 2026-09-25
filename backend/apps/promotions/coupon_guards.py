"""Quem pode mexer no cupom de um pedido — e até onde.

Duas guardas, e as duas protegem dinheiro que já se moveu. Ficam fora de
`coupon_service` porque respondem uma pergunta diferente: não é "este cupom vale
para este cliente?" (isso é `coupon_rules`), é "este pedido ainda aceita que
alguém mexa no total dele?".
"""

from decimal import Decimal

from apps.core.api_errors import CouponRejected


def recusar_pedido_encerrado(order):
    """Barra cupom em venda que já acabou.

    Três estados fecham a porta, cada um por um motivo diferente:

    - **pago integralmente**: a venda terminou e o cliente foi embora. Mexer no
      total agora criaria diferença de caixa sem contrapartida — o dinheiro que
      entrou não volta por causa de um cupom lembrado depois.
    - **cancelado / estornado**: não existe mais venda para descontar.
    - **bloqueado** (`is_locked`): alguém congelou o pedido de propósito.

    Conta PARCIALMENTE recebida continua aceitando: é justamente o caso do
    cliente que entrega o cupom no meio do pagamento, e o servidor confere
    depois se o total ainda cobre o que já entrou.
    """
    from apps.orders.models import Order

    if order.payment_status == Order.PAYMENT_PAID or order.status == Order.STATUS_PAID:
        raise CouponRejected("Esta venda já foi paga — o cupom não pode mais ser alterado.")
    if order.status in {Order.STATUS_CANCELLED, Order.STATUS_REFUNDED}:
        raise CouponRejected("Este pedido está cancelado.")
    if getattr(order, "is_locked", False):
        raise CouponRejected("Este pedido está bloqueado e não aceita alteração de cupom.")


def recusar_se_o_total_ficar_abaixo_do_recebido(order):
    """O desconto não pode ficar menor do que o dinheiro que já entrou.

    É a mesma guarda do fechamento, e ela existe porque um cupom aplicado no
    MEIO do pagamento muda o total para baixo: se o cliente já pagou R$ 60 de
    uma conta de R$ 60 e o cupom abate R$ 10, o caixa fica devendo R$ 10 que
    nenhum troco registrou. Quem tem de decidir isso é uma pessoa — estornando
    o recebimento antes.
    """
    from django.db.models import Sum

    from apps.payments.models import Payment

    recebido = order.payments.filter(status=Payment.STATUS_APPROVED).aggregate(
        valor=Sum("amount")
    )["valor"] or Decimal("0.00")
    if recebido > Decimal(order.total or 0):
        raise CouponRejected(
            f"O desconto deixaria o total menor do que o valor já recebido "
            f"({_reais(recebido)}). Estorne o recebimento antes de mexer no cupom."
        )


def _reais(valor):
    texto = f"{Decimal(valor or 0):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")
