"""O veredito "a loja está fora" — igual a `veredito_da_loja.dart` do PDV.

Caiu, FICA: 5 minutos na nuvem, e nenhuma resposta da loja no meio desfaz.
Vencida a janela, um ping decide: respondeu, volta; não, mais 5 minutos.
"""
import threading
import time


class Veredito:
    JANELA = 300.0

    def __init__(self):
        self._fora_desde = None
        self._trava = threading.Lock()

    def fora(self):
        with self._trava:
            return self._fora_desde is not None

    def precisa_conferir(self):
        with self._trava:
            return self._fora_desde is not None and time.monotonic() - self._fora_desde >= self.JANELA

    def respondeu(self):
        """Dentro da janela não traz de volta: só o ping depois dela."""
        with self._trava:
            if self._fora_desde is not None and time.monotonic() - self._fora_desde < self.JANELA:
                return
            self._fora_desde = None

    def caiu(self):
        with self._trava:
            self._fora_desde = time.monotonic()

    def voltou(self):
        with self._trava:
            self._fora_desde = None
