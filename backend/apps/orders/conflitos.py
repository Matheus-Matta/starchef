"""A recusa que diz para onde o caixa deve ir.

"A comanda 15 já está na conta #42" e "nada a cobrar" deixavam o caixa
procurando a conta na lista. A recusa leva um `code` e o pedido de destino; o
envelope da API (`core/envelope.py`) entrega os dois em `error`, e o PDV abre a
conta certa em vez de mostrar um erro.

Continua sendo `ValidationError`: quem só sabe tratar a recusa antiga segue
funcionando, com a mesma mensagem.
"""
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.response import Response


class ConflitoComDestino(ValidationError):
    def __init__(self, mensagem, *, code, **dados):
        super().__init__(mensagem)
        self.code_pdv = code
        self.dados = {chave: _texto(valor) for chave, valor in dados.items()}

    def resposta(self):
        """409: o corpo está certo, o estado é que não aceita."""
        return Response({"code": self.code_pdv, "message": self.messages[0], **self.dados},
                        status=status.HTTP_409_CONFLICT)


def destino(pedido_id):
    """Os dados do pedido para onde o PDV deve ir."""
    from apps.orders.models import Order

    pedido = Order.all_objects.filter(pk=pedido_id).values("id", "sequence", "status",
                                                           "payment_status").first()
    return {} if pedido is None else {"order_id": pedido["id"], "sequence": pedido["sequence"],
                                      "order_status": pedido["status"],
                                      "payment_status": pedido["payment_status"]}


def _texto(valor):
    if isinstance(valor, (list, tuple)):
        return [_texto(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _texto(v) for k, v in valor.items()}
    return valor if isinstance(valor, (str, int, float, bool, type(None))) else str(valor)
