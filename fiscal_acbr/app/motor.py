"""Qual motor atende: a ACBrLib de verdade ou a SEFAZ simulada.

Simulador quando pedido (`ACBR_SIMULADOR=1`) — e só então: subir simulando
sem ninguém ter pedido faria uma loja "emitir" notas que nunca existiram na
SEFAZ.

Sem a lib, o comunicador sobe com o motor [SemLib]: cada operação responde
`configuracao` com a providência, e o `/health` acusa 503. Antes ele nem
subia — no compose da loja, um container reiniciando em laço, e o caixa lendo
"comunicador fora do ar" sem pista de que faltava copiar um arquivo.
"""
import os

from app import sefaz
from app.simulador import Simulador


def criar_motor():
    if os.environ.get("ACBR_SIMULADOR") == "1":
        return Simulador()
    caminho = os.environ.get("ACBR_LIB_PATH", "/app/libs/libacbrnfe64.so")
    if not os.path.exists(caminho):
        return SemLib(caminho)
    from app.acbrlib import AcbrLib

    return AcbrLib(caminho, os.environ.get("ACBR_CONFIG", "/app/config/ACBrLib.ini"))


class SemLib:
    """O motor de quando a lib não está instalada: recusa tudo, explicando."""

    nome = "ausente"

    def __init__(self, caminho):
        self.mensagem = (
            f"ACBrLib não instalada: {caminho} não existe. Copie a libacbrnfe64.so "
            "(Projeto ACBr) para docker/local/acbr/libs no servidor da loja e reinicie "
            "o serviço fiscal-acbr (docs/FISCAL_ACBRLIB.md)."
        )

    def _recusar(self, _pedido):
        raise sefaz.FalhaDeConfiguracao(self.mensagem)

    status_servico = emitir = transmitir = consultar = cancelar = _recusar
