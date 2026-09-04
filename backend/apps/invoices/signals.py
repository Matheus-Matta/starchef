"""A nota fiscal nasce do pagamento, nao de um clique.

`apps.payments` avisa que o pedido foi quitado (`order_fully_paid`, ja depois
do commit) e e aqui que a NFC-e e emitida e mandada para a impressora. O
acoplamento fica so nesta direcao: o recebimento nao conhece o fiscal.
"""
from django.dispatch import receiver

from apps.orders.signals import order_fully_paid


@receiver(order_fully_paid, dispatch_uid="invoices_issue_on_full_payment")
def issue_invoice_on_full_payment(sender, order, user=None, auto_print=True, **kwargs):
    from apps.invoices.services import issue_invoice_for_paid_order

    issue_invoice_for_paid_order(order, user=user, auto_print=auto_print)
