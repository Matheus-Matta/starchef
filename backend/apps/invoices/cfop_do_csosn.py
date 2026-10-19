"""O CFOP da NFC-e do Simples Nacional sai do CSOSN (rejeição 386).

A SEFAZ só aceita certos pares na venda ao consumidor:

* CSOSN **500** (ICMS já cobrado por substituição) → CFOP 5405, 5656 ou 5667;
* CSOSN 101, 102, 103, 300, 400 e 900 → CFOP 5101, 5102, 5103, 5104 ou 5115.

O cadastro guarda os dois campos separados, e o par errado (500 com 5102,
102 com 5405) era recusado SEMPRE — reenviar repetia o mesmo par. O CSOSN é a
situação do produto, a parte que o contador decide; o CFOP da venda ao
consumidor é consequência dele. Por isso, o par que não combina vai com o CFOP
padrão do CSOSN, e o cadastro mantém o aviso. No Simples isso não mexe em
valor de imposto nenhum: muda só o código da operação.
"""
import logging

CFOP_COM_ST = frozenset({"5405", "5656", "5667"})
CFOP_SEM_ST = frozenset({"5101", "5102", "5103", "5104", "5115"})
CSOSN_SEM_ST = frozenset({"101", "102", "103", "300", "400", "900"})

logger = logging.getLogger(__name__)


def cfop_aceito(cfop, csosn):
    """O CFOP que a SEFAZ aceita com este CSOSN na NFC-e; o mesmo, se já serve."""
    if csosn == "500" and cfop not in CFOP_COM_ST:
        return "5405"
    if csosn in CSOSN_SEM_ST and cfop not in CFOP_SEM_ST:
        return "5102"
    return cfop


def ajustar(cfop, csosn, *, descricao=""):
    """`cfop_aceito`, registrando a troca para quem for corrigir o cadastro."""
    aceito = cfop_aceito(cfop, csosn)
    if aceito != cfop:
        logger.warning("NFC-e: CFOP %s não combina com CSOSN %s (%s); enviado %s (rejeição 386).",
                       cfop, csosn, descricao, aceito)
    return aceito
