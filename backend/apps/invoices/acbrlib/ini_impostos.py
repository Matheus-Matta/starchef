"""ICMS do item e os totais de ICMS/PIS/COFINS no INI da ACBrLib.

Produção, 20/11/2026, primeira venda em Regime Normal: "602 Rejeicao: Total do
PIS difere do somatorio dos itens sujeitos ao ICMS". A seção `[Total]` levava
só produtos, desconto e total da nota; a ACBrLib preenche o que falta com zero.
No Simples todo imposto destacado é zero e a soma batia por acaso. A Focus
calcula os totais do lado dela; aqui o XML nasce no backend, e cada total é a
soma do que vai nos itens — a mesma conta que a SEFAZ refaz.

O ICMS só entra (no item E no total) nos CST que têm `vICMS` no leiaute. Um
CST 60 com alíquota no perfil levava `pICMS`/`vICMS` que o grupo ICMS60 não
tem: o item saía sem ICMS e o total com ele (532).
"""
from decimal import Decimal

#: CST do regime normal cujo grupo traz vBC/pICMS/vICMS próprios.
CST_COM_ICMS = {"00", "10", "20", "51", "70", "90"}
#: No Simples, só o CSOSN 900 destaca ICMS próprio.
CSOSN_COM_ICMS = {"900"}


def destaca_icms(item, simples):
    if not item.get("icms_aliquota"):
        return False
    situacao = str(item.get("icms_situacao_tributaria") or "")
    return situacao in (CSOSN_COM_ICMS if simples else CST_COM_ICMS)


def icms(item, simples):
    situacao = item["icms_situacao_tributaria"]
    campos = {"orig": item["icms_origem"], ("CSOSN" if simples else "CST"): situacao}
    if destaca_icms(item, simples):
        campos.update({"modBC": "3",  # 3 = valor da operação (venda ao consumidor)
                       "vBC": item["icms_base_calculo"], "pICMS": item["icms_aliquota"],
                       "vICMS": item["icms_valor"]})
    return campos


def totais(items, simples):
    """vBC/vICMS/vPIS/vCOFINS da seção `[Total]`: a soma dos itens."""
    def soma(chave, filtro=lambda _item: True):
        return sum((Decimal(str(item.get(chave) or "0")) for item in items if filtro(item)),
                   start=Decimal("0.00"))

    com_icms = lambda item: destaca_icms(item, simples)  # noqa: E731
    return {
        "vBC": str(soma("icms_base_calculo", com_icms)),
        "vICMS": str(soma("icms_valor", com_icms)),
        "vPIS": str(soma("pis_valor")),
        "vCOFINS": str(soma("cofins_valor")),
    }
