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
    # A montada pela loja (/app/libs) vale primeiro; sem ela, a que a Action
    # embutiu na imagem (/opt/acbr, Secret ACBRLIB_SO_URL do fiscal_acbr.yml).
    montada = os.environ.get("ACBR_LIB_PATH", "/app/libs/libacbrnfe64.so")
    embutida = os.environ.get("ACBR_LIB_EMBUTIDA", "/opt/acbr/libacbrnfe64.so")
    caminho = next((c for c in (montada, embutida) if os.path.exists(c)), None)
    if caminho is None:
        return SemLib(montada)
    # A ACBrLib valida o XML contra os Schemas da NF-e ANTES de enviar
    # (`PathSchemas` no ACBrLib.ini). Sem a pasta, toda nota falhava nessa
    # validação com uma mensagem técnica — melhor dizer o que falta.
    schemas = os.environ.get("ACBR_SCHEMAS", "/app/libs/Schemas")
    if not os.path.isdir(schemas):
        return SemLib(
            caminho,
            motivo=f"faltam os Schemas da NF-e em {schemas} (a pasta Schemas/NFe "
            "da distribuição da ACBr)",
        )
    from app import acbrlib

    try:
        return acbrlib.AcbrLib(caminho, os.environ.get("ACBR_CONFIG", "/app/config/ACBrLib.ini"))
    except (OSError, sefaz.FalhaFiscal) as erro:
        # Arquivo corrompido, de outra arquitetura, ou que não inicializa: sem
        # isto o container caía no boot e reiniciava em laço, calado.
        return SemLib(caminho, motivo=f"a lib não carregou ({erro})")


class SemLib:
    """O motor de quando a lib não está instalada: recusa tudo, explicando."""

    nome = "ausente"

    def __init__(self, caminho, motivo=None):
        self.mensagem = (
            f"ACBrLib não instalada: {motivo or f'{caminho} não existe'}. Copie a "
            "libacbrnfe64.so e a pasta Schemas (Projeto ACBr) para acbr/libs no "
            "servidor e reinicie o serviço fiscal-acbr (docs/FISCAL_ACBRLIB.md)."
        )

    def _recusar(self, _pedido):
        raise sefaz.FalhaDeConfiguracao(self.mensagem)

    status_servico = emitir = transmitir = consultar = cancelar = _recusar
