"""Os recebimentos ESTORNADOS de uma sessão de caixa (pedido pago cancelado).

Entram na sessão em que foram VENDIDOS — é contra a maquininha daquele turno
que o gerente confere. A saída do dinheiro da gaveta é outra coisa: é o
movimento de estorno, que pode cair no caixa aberto agora
(`estorno_do_pedido.py`).
"""
from decimal import Decimal

from django.db.models import Q

from apps.payments.models import CashMovement, Payment


def estornos_da_sessao(session):
    vendidos_aqui = Q(metadata__cash_register=str(session.pk)) | Q(
        cash_movements__cash_register_id=session.pk,
        cash_movements__movement_type=CashMovement.TYPE_SALE,
    )
    return (
        Payment.objects.filter(status=Payment.STATUS_REFUNDED)
        .filter(vendidos_aqui)
        .select_related("payment_method", "order")
        .distinct()
        .order_by("updated_at")
    )


def estornos_do_extrato(session):
    """O bloco de estornos do extrato da sessão (tela do caixa na retaguarda)."""
    linhas = [
        {
            "id": str(payment.pk),
            "order": str(payment.order_id),
            "order_sequence": payment.order.sequence,
            "payment_method_name": payment.payment_method.name,
            "method_type": payment.payment_method.method_type,
            "card_subtype": payment.card_subtype,
            "amount": str(payment.amount),
            "cancel_reason": payment.order.cancel_reason,
            "refunded_at": payment.order.cancelled_at,
        }
        for payment in estornos_da_sessao(session)
    ]
    total = sum((Decimal(linha["amount"]) for linha in linhas), Decimal("0.00"))
    return {"refunds": linhas, "refunds_total": str(total), "refunds_count": len(linhas)}
