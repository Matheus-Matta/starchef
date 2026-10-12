"""A SEFAZ simulada nunca se passa pela de verdade.

Na nuvem de teste o simulador respondia "Autorizado o uso da NF-e" — a frase
da SEFAZ real — e autorizava até em PRODUÇÃO. Toda nota saía "emitida", com
protocolo e QR Code que não levavam a lugar nenhum, e quem testava concluía
que a emissão funcionava.
"""
from tests.test_api import CONTEXTO, INI


def _emitir(api, ambiente):
    return api.post("/v1/nfe/emitir", json={**CONTEXTO, "ambiente": ambiente,
                                            "tp_emis": "1", "ini": INI.format(tp=1)})


def test_producao_e_recusada_com_o_motivo(api):
    resposta = _emitir(api, "1")

    assert resposta.status_code == 500
    assert resposta.json()["erro"] == "configuracao"
    assert "SIMULADA" in resposta.json()["mensagem"]
    assert "PRODUÇÃO" in resposta.json()["mensagem"]


def test_homologacao_autoriza_dizendo_que_e_simulado(api):
    resposta = _emitir(api, "2")

    assert resposta.status_code == 200
    assert resposta.json()["situacao"] == "autorizada"
    assert "SIMULADO" in resposta.json()["motivo"]
    assert "sem valor fiscal" in resposta.json()["motivo"]
