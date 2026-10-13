"""O fuso do dhEmi é dito à ACBrLib, nunca adivinhado por ela.

O backend manda a data de emissão SEM fuso (`dd/mm/aaaa hh:mm:ss`, horário de
Brasília) e a ACBrLib acrescenta o fuso. Ela o lê do sistema (/etc/timezone),
que no container é UTC: a nota das 22:36 saía `22:36:00+00:00` — 19:36 em
Brasília — e a SEFAZ recusava com 704, "Data-Hora de emissão atrasada".
"""
from app.acbrlib import AcbrLib, fuso_local
from app.modelos import Emitir


class LibFalsa:
    def __init__(self):
        self.gravados = {}

    def NFE_ConfigGravarValor(self, _handle, secao, chave, valor):
        self.gravados[(secao.decode(), chave.decode())] = valor.decode()
        return 0


def _motor():
    motor = AcbrLib.__new__(AcbrLib)
    motor.lib = LibFalsa()
    motor.handle = None
    return motor


def _pedido(**extra):
    return Emitir(uf="SP", cnpj="11222333000181", ini="", **extra)


def test_o_fuso_vai_em_modo_manual_com_o_que_o_backend_mandou():
    motor = _motor()
    motor._configurar(_pedido(fuso="-04:00"))
    assert motor.lib.gravados[("DFe", "TimeZone.Modo")] == "2"
    assert motor.lib.gravados[("DFe", "TimeZone.Str")] == "-04:00"


def test_backend_antigo_sem_fuso_usa_o_do_container(monkeypatch):
    """O TZ do container é America/Sao_Paulo (Dockerfile): -03:00, e não UTC."""
    monkeypatch.setenv("TZ", "America/Sao_Paulo")
    motor = _motor()
    motor._configurar(_pedido())
    assert motor.lib.gravados[("DFe", "TimeZone.Str")] == fuso_local()
    assert len(fuso_local()) == 6 and fuso_local()[3] == ":"
