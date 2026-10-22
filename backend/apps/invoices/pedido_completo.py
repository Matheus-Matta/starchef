"""A NFC-e só é montada com o pedido INTEIRO na mão.

A venda feita na nuvem chega à loja em pedaços: o pedido, os itens e os
pagamentos são eventos separados da sincronização. A varredura dos pagos sem
nota (`emissao_da_loja.emitir_pagos_sem_nota`) pegava o pedido no meio do
caminho, e a nota nascia:

- sem itens — "a nota nao possui itens fiscais";
- sem pagamento — o documento ia com tPag=90 ("sem pagamento"), que a NFC-e
  não aceita: rejeição 899, "Informado incorretamente o campo meio de
  pagamento". Pagamento menor que o total é a 865.

Mandar à SEFAZ o que ela vai recusar só gasta tentativa e esconde a causa.
Aqui a pergunta é feita antes, e a resposta diz o que falta.
"""
from decimal import Decimal

from apps.orders.models import OrderItem

ESPERE_A_SINCRONIZACAO = "Se a venda veio da nuvem, espere a sincronização terminar e reenvie."


# `all_objects` filtrado pelo pedido: a varredura roda sem conta corrente, e o
# gerenciador do tenant devolveria vazio — todo pedido pareceria sem itens.
def itens_cobraveis(order):
    return OrderItem.all_objects.filter(order_id=order.pk, deleted_at__isnull=True).exclude(
        status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED])


def pago_aprovado(order) -> Decimal:
    from apps.payments.models import Payment

    valores = Payment.all_objects.filter(order_id=order.pk, status=Payment.STATUS_APPROVED,
                                         deleted_at__isnull=True).values_list("amount", flat=True)
    return sum(valores, start=Decimal("0.00"))


def motivo_sem_itens(order):
    if itens_cobraveis(order).exists():
        return None
    return f"O pedido ainda não tem itens neste servidor. {ESPERE_A_SINCRONIZACAO}"


def motivo_sem_pagamento(order, total):
    """Por que os pagamentos não fecham a NFC-e de `total` — ou `None`."""
    total = Decimal(total)
    if total <= 0:
        return "Pedido de valor zero não gera NFC-e: a SEFAZ exige um meio de pagamento com valor."
    pago = pago_aprovado(order)
    if pago <= 0:
        return f"O pedido não tem pagamento aprovado neste servidor. {ESPERE_A_SINCRONIZACAO}"
    if pago < total:
        return (f"Os pagamentos aprovados somam R$ {pago:.2f}, menos que o total de "
                f"R$ {total:.2f}. {ESPERE_A_SINCRONIZACAO}")
    return None


def motivo_do_pedido_incompleto(order):
    """O que falta para a NFC-e deste pedido sair — ou `None` se está inteiro."""
    return motivo_sem_itens(order) or motivo_sem_pagamento(order, order.total)
