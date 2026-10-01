"""Cancelar vários pedidos de uma vez, com a regra do cancelamento de um.

O cancelamento individual (`OrderViewSet.cancel`) já faz tudo o que importa:
cancela a nota fiscal do pedido, os pagamentos e o caixa. Este módulo NÃO
reimplementa nada disso — ele só repete aquele gesto pedido a pedido, com a
mesma autorização:

- pedido vazio ou dentro da carência: cancela sem senha (nada chegou à
  produção, não há consumo a proteger);
- os outros: exigem a senha de operação do restaurante ou um usuário com
  permissão de cancelar.

Cada pedido cancela na PRÓPRIA transação. Um que falhe (já pago e sem
autorização, nota que a SEFAZ recusa cancelar) não desfaz os outros, e a
resposta diz qual ficou de fora e por quê.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.orders.models import Order

#: Teto por chamada: cancelar é gesto pesado (nota, pagamento, caixa).
MAXIMO = 500

_FINAIS = {Order.STATUS_CANCELLED, Order.STATUS_REFUNDED}


def cancelar_em_massa(pedidos, *, user, reason, autorizar):
    """`autorizar(pedido)` devolve `(autorizado, quem, como)`, como a view."""
    from apps.orders.services import cancel_order, order_is_empty, order_within_cancellation_grace

    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("O motivo do cancelamento é obrigatório.")

    resultado = {"cancelled": 0, "skipped": []}
    # Ordem estável (por id) para dois cancelamentos em massa simultâneos
    # travarem as linhas na mesma sequência, e não um esperando o outro.
    for pedido in sorted(pedidos, key=lambda p: str(p.pk)):
        if pedido.status in _FINAIS:
            resultado["skipped"].append(_pulo(pedido, "já estava cancelado"))
            continue
        if order_within_cancellation_grace(pedido):
            autorizado, quem, como = True, None, Order.AUTHORIZATION_GRACE
        else:
            autorizado, quem, como = autorizar(pedido)
        if not autorizado and not order_is_empty(pedido):
            resultado["skipped"].append(_pulo(pedido, "precisa da senha de operação"))
            continue
        try:
            with transaction.atomic():
                cancel_order(
                    pedido, user, reason,
                    authorized_by=quem,
                    authorization=como or Order.AUTHORIZATION_OWN,
                )
            resultado["cancelled"] += 1
        except ValidationError as exc:
            resultado["skipped"].append(_pulo(pedido, " ".join(exc.messages)))
    return resultado


def _pulo(pedido, motivo):
    return {"id": str(pedido.pk), "sequence": pedido.sequence, "reason": motivo}
