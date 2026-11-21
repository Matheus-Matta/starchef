"""Os códigos fiscais com o tamanho que a SEFAZ e a ACBrLib exigem.

Produção, 20/11/2026: "ACBrLib: Valor string inválido para TCSTPIS: 4". O
CST do PIS/COFINS tem 2 dígitos ("04"), mas a planilha importada passou pelo
Excel, que lê o código como número e apaga o zero à esquerda. O CST do ICMS
"00" virava "0" do mesmo jeito.

Completa nos DOIS lugares: ao salvar o perfil (a próxima importação já grava
certo) e ao montar a nota (o perfil gravado antes da correção também emite,
sem reimportar). Só completa dígitos mais curtos que o código; o resto passa
intacto e a validação de cada campo decide.
"""
from apps.invoices.ibs_cbs import completar_zeros

#: Campo do perfil (e do item da nota) → quantos dígitos o código tem.
TAMANHOS = {
    "cst_icms": 2,
    "csosn": 3,
    "pis_cst": 2,
    "cofins_cst": 2,
    "ibs_cbs_cst": 3,
    "ibs_cbs_cclass_trib": 6,
    # 21/11/2026: "CEST '300504' ... pattern [0-9]{7}" — o 03.005.04 do Excel.
    # O NCM tem o mesmo risco (capítulos 01 a 09: carne, leite, café).
    "ncm": 8,
    "cest": 7,
}


def completar_codigos(attrs):
    """Os códigos de `attrs` (dict do serializer) com o zero à esquerda de volta."""
    for campo, tamanho in TAMANHOS.items():
        if attrs.get(campo):
            attrs[campo] = completar_zeros(attrs[campo], tamanho)
    return attrs


def codigo(valor, campo):
    """Um código só, no tamanho do campo: `codigo("4", "pis_cst")` → "04"."""
    return completar_zeros(valor, TAMANHOS[campo]) if valor else valor


#: CST do PIS/COFINS sem valor no leiaute (grupos PISNT/COFINSNT): 04 a 09.
#: 21/11/2026: refrigerante com CST 04 (monofásico) e alíquota no perfil — o
#: valor ia ao total da nota e a ACBrLib o descartava no item (rejeição 602).
CST_PIS_COFINS_SEM_VALOR = {"04", "05", "06", "07", "08", "09"}


def pis_cofins_tem_valor(cst):
    return codigo(cst, "pis_cst") not in CST_PIS_COFINS_SEM_VALOR


def perfil_tem_valor_pis_cofins(perfil, campo):
    return bool(perfil) and pis_cofins_tem_valor(getattr(perfil, campo))
