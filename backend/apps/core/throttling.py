"""Limite de requisições com uma faixa própria para os terminais do PDV.

O PDV desktop, o app do garçom e o PDV web consultam o servidor o dia inteiro
(fila de impressão, pedidos, comandas, KDS), e vários terminais costumam usar o
MESMO usuário. Com o limite comum por usuário (2000/hora) a loja batia no teto
no meio do serviço, e o terminal passava a receber 429 — impressão e pedido
parados.

O terminal se identifica pelo cabeçalho `X-Terminal-Id`, que os três clientes
mandam em toda requisição. Ele ganha uma faixa 100x maior, CONTADA À PARTE do
painel. Login, troca de senha e senha de caixa têm limites próprios e
continuam apertados: são eles que seguram tentativa de adivinhar senha.
"""
from rest_framework.throttling import UserRateThrottle


class TerminalScopeMixin:
    """Troca o escopo para `terminal_scope` quando a requisição vem de terminal."""

    terminal_scope = None

    def allow_request(self, request, view):
        if self.terminal_scope and request.headers.get("X-Terminal-Id"):
            self.scope = self.terminal_scope
            self.rate = self.get_rate()
            self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)


class TerminalAwareUserRateThrottle(TerminalScopeMixin, UserRateThrottle):
    """O limite geral por usuário, com a faixa larga dos terminais."""

    terminal_scope = "terminal_user"
