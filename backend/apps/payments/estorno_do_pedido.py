"""Estorno dos recebimentos de um pedido PAGO que foi cancelado.

Cancelar uma venda paga é devolver o dinheiro ao cliente. Antes, o pedido só
ganhava a marca "estornado" e os recebimentos seguiam aprovados: o fechamento
somava a venda desfeita no crédito e cobrava do operador, na gaveta, a nota que
ele devolveu.

O recebimento vira `refunded` (não `cancelled`): o dinheiro ENTROU e SAIU, e o
relatório do caixa mostra as duas pontas. Por isso, no dinheiro, a venda não é
apagada — entra um movimento de estorno negativo ao lado dela.
"""
from decimal import Decimal

from django.db.models import Sum

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.payments.models import CashMovement, Payment, PaymentMethod
from apps.payments.terminals import active_session_for_user


def _sessao_que_devolve(sessao_da_venda, restaurante, user):
    """A gaveta de onde a nota sai: a da venda, se ainda aberta.

    Sessão já fechada não recebe movimento — o esperado dela foi gravado no
    fechamento e o papel assinado deixaria de bater. A devolução sai do caixa
    que o operador tem aberto agora; sem nenhum, fica na sessão da venda, que
    é a única que conhece esse dinheiro.
    """
    if not sessao_da_venda.is_finished:
        return sessao_da_venda
    return active_session_for_user(restaurante, user) or sessao_da_venda


def _devolver_da_gaveta(payment, *, user, reason):
    movimentos = payment.cash_movements.select_for_update().filter(status="approved")
    venda = movimentos.filter(movement_type=CashMovement.TYPE_SALE).select_related("cash_register").first()
    if venda is None:
        return None
    # O líquido que ficou na gaveta (venda menos troco), e não a nota entregue.
    liquido = movimentos.aggregate(v=Sum("amount"))["v"] or Decimal("0.00")
    if liquido <= 0:
        return None
    sessao = _sessao_que_devolve(venda.cash_register, payment.order.restaurant, user)
    return CashMovement.objects.create(
        account=payment.account,
        restaurant=payment.restaurant,
        branch=payment.branch,
        cash_register=sessao,
        payment=payment,
        operator=user,
        movement_type=CashMovement.TYPE_REFUND,
        # NEGATIVO, como toda saída: o esperado é a soma direta dos movimentos.
        amount=-liquido,
        reason=f"Estorno do pedido {payment.order.sequence}: {reason}"[:1000],
        metadata={"event": "order_cancelled_refund", "sale_session": str(venda.cash_register_id)},
        created_by=user,
        updated_by=user,
    )


def estornar_recebimentos_do_pedido(order, *, user, reason):
    """Estorna cada recebimento aprovado; idempotente (o estornado não volta)."""
    recebimentos = (
        order.payments.select_for_update()
        .filter(status=Payment.STATUS_APPROVED)
        .select_related("payment_method")
        .order_by("pk")
    )
    for payment in recebimentos:
        payment.status = Payment.STATUS_REFUNDED
        payment.updated_by = user
        payment.save(update_fields=["status", "updated_by", "updated_at"])
        if payment.payment_method.method_type == PaymentMethod.TYPE_CASH:
            _devolver_da_gaveta(payment, user=user, reason=reason)
        record_audit(
            action=AuditLog.ACTION_CANCELLED,
            instance=payment,
            actor=user,
            reason=reason,
            metadata={"order": str(order.id), "event": "payment_refunded"},
        )
