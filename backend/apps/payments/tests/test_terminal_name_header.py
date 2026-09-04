# -*- coding: utf-8 -*-
"""O nome do terminal atravessa o cabecalho sem perder acento.

Cabecalho HTTP nao carrega UTF-8. Os clientes percent-encodam o valor quando
ele tem acento (senao o cliente Dart estoura antes de enviar, e o navegador
manda latin-1 cru); aqui a ponta do servidor precisa desfazer isso.
"""
from django.test import RequestFactory, SimpleTestCase

from apps.payments.terminals import terminal_name_from_request


class TerminalNameHeaderTests(SimpleTestCase):
    def _request(self, header):
        return RequestFactory().post("/", HTTP_X_TERMINAL_NAME=header)

    def test_percent_encoded_volta_com_acento(self):
        request = self._request("Caixa%20Secund%C3%A1rio%20ab12cd")

        self.assertEqual(
            terminal_name_from_request(request), "Caixa Secundário ab12cd"
        )

    def test_nome_ascii_atravessa_igual(self):
        # Um cliente que ainda nao encoda continua sendo entendido: `unquote`
        # de um texto sem `%` devolve o proprio texto.
        request = self._request("Caixa Principal ab12cd")

        self.assertEqual(
            terminal_name_from_request(request), "Caixa Principal ab12cd"
        )

    def test_sem_cabecalho_devolve_vazio(self):
        self.assertEqual(terminal_name_from_request(RequestFactory().post("/")), "")
