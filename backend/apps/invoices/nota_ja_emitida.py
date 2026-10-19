"""A nota que o pedido JÁ tem, como resposta do `/invoices/emit/`.

Emitir é idempotente por pedido: pedir a nota de um pedido que já tem uma
pendente ou autorizada devolve ESSA nota. Fica à parte porque a view precisa
fazer a pergunta duas vezes — antes de emitir e de novo quando a emissão
recusa porque a automática (`order_fully_paid`, em segundo plano) gravou a
nota enquanto esta requisição esperava a trava do pedido.
"""
from rest_framework import status
from rest_framework.response import Response

from apps.invoices.models import Invoice


def responder_com_a_nota_existente(order, request, *, by_terminal):
    """`Response` com a nota do pedido, ou `None` quando ele não tem nenhuma.

    Lida do BANCO, e não de `order.invoice`: o pedido em memória foi carregado
    antes de a outra emissão gravar, e não enxerga a nota dela.
    """
    from apps.invoices.serializers import InvoiceSerializer
    from apps.invoices.services import mark_terminal_prints, with_fiscal_state

    nota = Invoice.all_objects.filter(
        order=order, status__in=(Invoice.STATUS_PENDING, Invoice.STATUS_ISSUED),
    ).first()
    if nota is None:
        return None
    if by_terminal and mark_terminal_prints(nota):
        nota.save(update_fields=["fiscal_payload", "updated_at"])
    data = with_fiscal_state(InvoiceSerializer(nota, context={"request": request}).data, nota)
    return Response(data, status=status.HTTP_200_OK)
