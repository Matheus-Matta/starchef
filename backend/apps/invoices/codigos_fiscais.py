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
