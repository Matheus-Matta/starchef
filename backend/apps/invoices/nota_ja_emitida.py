"""A nota que o pedido JÁ tem, como resposta do `/invoices/emit/`.

Emitir é idempotente por pedido: pedir a nota de um pedido que já tem uma
pendente ou autorizada devolve ESSA nota. Fica à parte porque a view precisa
fazer a pergunta duas vezes — antes de emitir e de novo quando a emissão
recusa porque a automática (`order_fully_paid`, em segundo plano) gravou a
nota enquanto esta requisição esperava a trava do pedido.
"""
import time

from django.db import connection
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
    nota = _esperar_a_transmissao(nota)
    if by_terminal and mark_terminal_prints(nota):
        nota.save(update_fields=["fiscal_payload", "updated_at"])
    data = with_fiscal_state(InvoiceSerializer(nota, context={"request": request}).data, nota)
    return Response(data, status=status.HTTP_200_OK)


#: Quanto o `/invoices/emit/` espera a transmissão em curso terminar. Abaixo
#: dos 20 s do PDV: passando disto ele recebe a nota "processando" e segue
#: consultando (`refresh-status`) em segundo plano.
ESPERA_DA_TRANSMISSAO_S = 12
_INTERVALO_S = 0.25


def _esperar_a_transmissao(nota):
    """A nota que a emissão automática está transmitindo AGORA, já respondida.

    Antes o PDV esperava a mesma coisa parado na trava do pedido, segurando
    uma transação e uma conexão do banco. Aqui espera relendo a nota, sem
    trava e sem transação: o caso comum (SEFAZ em 1-3 s) devolve a nota
    autorizada e o DANFE sai na hora, sem o aviso de "aguardando autorização"
    a cada venda.
    """
    from apps.invoices.services import em_voo_recente

    limite = time.monotonic() + ESPERA_DA_TRANSMISSAO_S
    while em_voo_recente(nota) and time.monotonic() < limite:
        if not connection.in_atomic_block:
            # Devolve a conexão ao pool durante a espera.
            connection.close()
        time.sleep(_INTERVALO_S)
        nota = Invoice.all_objects.filter(pk=nota.pk).first() or nota
    return nota
