"""Limite de requisições com uma faixa própria para os terminais do PDV.

O PDV desktop, o app do garçom e o PDV web consultam o servidor o dia inteiro
(fila de impressão, pedidos, comandas, KDS), e vários terminais costumam usar o
MESMO usuário. Com o limite comum por usuário (2000/hora) a loja batia no teto
no meio do serviço, e o terminal passava a receber 429 — impressão e pedido
parados.

O terminal se identifica pelo cabeçalho `X-Terminal-Id`, que os três clientes
mandam em toda requisição. Logado, ele não passa por limite nenhum. Login,
troca de senha e senha de caixa têm limites próprios e continuam apertados: são
eles que seguram tentativa de adivinhar senha.
"""
from rest_framework.throttling import UserRateThrottle


class TerminalScopeMixin:
    """Terminal LOGADO não tem limite; o resto segue o escopo normal.

    Um 429 no meio do serviço é impressão e pedido parados, e o terminal não
    tem como esperar.
    O usuário já está autenticado — o abuso que este limite contém é o de
    quem não está, e esse continua barrado (anônimo, login, senha de caixa).
    """

    terminal_scope = None

    def allow_request(self, request, view):
        user = getattr(request, "user", None)
        if request.headers.get("X-Terminal-Id") and getattr(user, "is_authenticated", False):
            return True
        return super().allow_request(request, view)


class TerminalAwareUserRateThrottle(TerminalScopeMixin, UserRateThrottle):
    """O limite geral por usuário; terminal logado passa direto."""

    terminal_scope = "terminal_user"
