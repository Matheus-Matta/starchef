"""O veredito "a loja está fora" — igual a `veredito_da_loja.dart` do PDV.

Janela de 30 s que dobra a cada recaída (até 5 min) e volta aos 30 s quando a
loja fica de pé por 5 min.
"""
import threading
import time


class Veredito:
    BASE, TETO, ESTABILIDADE = 30.0, 300.0, 300.0

    def __init__(self):
        self._fora_desde = self._voltou_em = None
        self._estava_fora = False
        self._recaidas = 0
        self._trava = threading.Lock()

    def janela(self):
        return min(self.BASE * (2 ** min(self._recaidas, 4)), self.TETO)

    def fora(self):
        with self._trava:
            if self._fora_desde is None:
                return False
            if time.monotonic() - self._fora_desde > self.janela():
                self._fora_desde = None
                return False
            return True

    def respondeu(self):
        with self._trava:
            if self._estava_fora:
                self._voltou_em, self._estava_fora = time.monotonic(), False
            self._fora_desde = None

    def caiu(self):
        with self._trava:
            agora = time.monotonic()
            recaiu = self._voltou_em is not None and agora - self._voltou_em < self.ESTABILIDADE
            self._recaidas = self._recaidas + 1 if recaiu else 0
            self._fora_desde, self._estava_fora = agora, True
