"""O pedido pago que toda NFC-e de teste precisa.

A NFC-e não sai sem um meio de pagamento que cubra o total (899/865,
`pedido_completo.py`): os testes que só queriam "um pedido para emitir" ganham
um pagamento em dinheiro, exato, sem troco.
"""
from apps.payments.models import Payment, PaymentMethod

NOME_DO_METODO = "Pagamento do teste"


def quitar_pedido(order):
    order.refresh_from_db()
    metodo, _ = PaymentMethod.all_objects.get_or_create(
        account=order.account, restaurant=order.restaurant, branch=order.branch,
        name=NOME_DO_METODO, defaults={"method_type": PaymentMethod.TYPE_CASH},
    )
    return Payment.all_objects.create(
        account=order.account, restaurant=order.restaurant, branch=order.branch,
        order=order, payment_method=metodo, amount=order.total, status=Payment.STATUS_APPROVED,
    )


def desfazer_quitacao(order):
    """Para o teste que monta os próprios pagamentos."""
    Payment.all_objects.filter(order=order, payment_method__name=NOME_DO_METODO).delete()
