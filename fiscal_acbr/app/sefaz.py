"""O que um cStat da SEFAZ significa para o backend.

A ACBrLib devolve `0` quando a CHAMADA deu certo — isso não é autorização. Quem
diz o destino da nota é o cStat da resposta, e é aqui que ele vira a
`situacao` do contrato.
"""
AUTORIZADA = {"100", "150"}
DENEGADA = {"110", "301", "302", "303"}
# Duplicidade: a nota JÁ EXISTE na SEFAZ. Nunca é recusa — o comunicador
# consulta e devolve a situação real (`motor.emitir`).
DUPLICIDADE = {"204", "539"}
NAO_ENCONTRADA = {"217", "562"}
PROCESSANDO = {"103", "104", "105"}
CANCELADA = {"101", "135", "155"}
# Serviço paralisado: é indisponibilidade, não recusa — justifica contingência.
PARALISADA = {"108", "109"}


class FalhaFiscal(Exception):
    """Base das falhas que o contrato devolve com `erro` (ver `main._ERROS`)."""


class FalhaDeComunicacao(FalhaFiscal):
    """Não alcançou a SEFAZ antes de enviar: seguro tentar de novo/contingência."""


class FalhaIncerta(FalhaFiscal):
    """A resposta se perdeu depois do envio: a SEFAZ pode ter autorizado."""


class DocumentoInvalido(FalhaFiscal):
    """Schema, assinatura ou INI inválidos — repetir dá o mesmo erro."""


class FalhaDeConfiguracao(FalhaFiscal):
    """Certificado, CSC ou biblioteca: nenhuma nota sai até corrigir."""


def situacao(cstat):
    cstat = str(cstat or "").strip()
    if cstat in AUTORIZADA:
        return "autorizada"
    if cstat in DENEGADA:
        return "denegada"
    if cstat in NAO_ENCONTRADA:
        return "nao_encontrada"
    if cstat in PROCESSANDO:
        return "processando"
    if cstat in CANCELADA:
        return "cancelada"
    if cstat in PARALISADA:
        raise FalhaDeComunicacao(f"SEFAZ com o serviço paralisado (cStat {cstat}).")
    return "rejeitada"
