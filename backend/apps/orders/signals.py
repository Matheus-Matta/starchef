"""Sinais de dominio do pedido.

Ficam aqui, e nao em `events.py`, porque `events.py` cuida do transporte
(WebSocket) e estes sao fatos do negocio: quem escuta decide o que fazer com
eles. E o que permite a nota fiscal nascer do pagamento sem que `apps.payments`
precise conhecer `apps.invoices`.
"""
import django.dispatch

# O pedido foi quitado (o ultimo recebimento cobriu o total).
#
# Argumentos: `order` (ja salvo como pago) e `user` (quem recebeu).
# Enviado SEMPRE depois do commit — quem escuta emite nota e imprime, duas
# operacoes com efeito externo que nao podem acontecer dentro da transacao do
# recebimento nem sobreviver a um rollback dela.
order_fully_paid = django.dispatch.Signal()
