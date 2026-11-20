"""Duplicidade nunca consulta a SEFAZ com a chave vazia.

Produção, 20/11/2026: "ACBrLib: Chave "" inválida". A 539 (número já
autorizado com OUTRA chave) era tratada como duplicidade desta nota: o
comunicador consultava a própria chave, que veio vazia, e a lib recusava a
consulta. A recusa da SEFAZ, com a chave dela entre colchetes, nunca chegava
ao backend — que sabe resolver a 539 (`numero_ja_usado.py`).
"""
from app.acbrlib import AcbrLib

CHAVE_DA_SEFAZ = "33261163201558000155650010000000011544547967"


def _lib(resposta_do_envio, xml=""):
    lib = AcbrLib.__new__(AcbrLib)
    lib.consultadas = []
    lib.lib = type("Lib", (), {"NFE_Enviar": None})()
    lib._texto = lambda _funcao, *_args: resposta_do_envio
    lib._xml_atual = lambda: xml
    lib._consultar_chave = lambda _pedido, chave: lib.consultadas.append(chave) or {"situacao": "autorizada"}
    return lib


def test_539_volta_como_recusa_com_a_chave_da_sefaz():
    lib = _lib(f"[NFe1]\ncStat=539\nxMotivo=Rejeicao: Duplicidade de NF-e com diferenca na Chave "
               f"de Acesso [chNFe:{CHAVE_DA_SEFAZ}]\n")

    resultado = lib._enviar(pedido=None)

    assert lib.consultadas == []
    assert resultado["situacao"] == "rejeitada"
    assert CHAVE_DA_SEFAZ in resultado["motivo"]


def test_204_sem_chave_volta_a_recusa_em_vez_de_consultar_vazio():
    lib = _lib("[Envio]\ncStat=204\nxMotivo=Rejeicao: Duplicidade de NF-e\n")

    resultado = lib._enviar(pedido=None)

    assert lib.consultadas == []
    assert resultado["situacao"] == "rejeitada" and resultado["cstat"] == "204"


def test_204_com_a_chave_continua_consultando():
    lib = _lib(f"[NFe1]\ncStat=204\nchDFe={CHAVE_DA_SEFAZ}\n")

    assert lib._enviar(pedido=None) == {"situacao": "autorizada"}
    assert lib.consultadas == [CHAVE_DA_SEFAZ]
