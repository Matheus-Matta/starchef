"""A nota fiscal nasce do pagamento, nao de um clique.

`apps.payments` avisa que o pedido foi quitado (`order_fully_paid`, ja depois
do commit) e e aqui que a NFC-e e emitida e mandada para a impressora. O
acoplamento fica so nesta direcao: o recebimento nao conhece o fiscal.

A EMISSAO VAI PARA A FILA, e nao roda aqui. Este receptor executa dentro da
requisicao que concluiu a venda (o `on_commit` roda antes de a resposta sair),
e emitir aqui fazia o caixa esperar a SEFAZ inteira — de 1 s a 40 s — para a
tela liberar. Passando de 20 s o PDV desistia, repetia, saia da tela, e o
DANFE se perdia na corrida com a emissao que ainda estava na SEFAZ.
"""
import logging

from django.dispatch import receiver
from kombu.exceptions import OperationalError

from apps.orders.signals import order_fully_paid


@receiver(order_fully_paid, dispatch_uid="invoices_issue_on_full_payment")
def issue_invoice_on_full_payment(sender, order, user=None, auto_print=True, **kwargs):
    from apps.invoices.tasks import emitir_nota_do_pedido_pago_task

    try:
        emitir_nota_do_pedido_pago_task.delay(
            str(order.pk), str(user.pk) if user is not None else None, auto_print)
    except OperationalError:
        # Sem o Redis a fila nao existe. Esperar a SEFAZ e ruim; venda paga
        # sem nota e pior — emite aqui, como antes.
        logging.getLogger(__name__).warning(
            "Fila do Celery fora: NFC-e do pedido %s emitida na requisicao", order.pk)
        from apps.invoices.services import issue_invoice_for_paid_order

        issue_invoice_for_paid_order(order, user=user, auto_print=auto_print)
