"""O grupo IBS/CBS do documento neutro no leiaute INI da ACBrLib.

Nomes de seção e chave conferidos no `ACBrNFe.IniReader.pas` (frones/ACBr,
master). Três detalhes do leitor que mudam o INI:

* os grupos são seções SOLTAS com o número do item (`gIBSUF001`), não
  aninhadas em `IBSCBS001`;
* redução (`pRedAliq`/`pAliqEfet`) e diferimento (`pDif`/`vDif`) são chaves
  dentro de `gIBSUF`/`gIBSMun`/`gCBS`, não seções;
* `gIBSUF`/`gIBSMun`/`gCBS` só são lidos se `gIBSCBS` existir — sem ela os
  valores somem em silêncio.

Os totais da nota são a SOMA dos valores já arredondados de cada item.
"""
from decimal import Decimal

#: Seção do item → (prefixo no documento, chave da alíquota, chave do valor).
GRUPOS = (
    ("gIBSUF", "ibs_uf", "pIBSUF", "vIBSUF"),
    ("gIBSMun", "ibs_mun", "pIBSMun", "vIBSMun"),
    ("gCBS", "cbs", "pCBS", "vCBS"),
)


def _d(item, chave):
    return Decimal(item.get(chave) or "0")


def secoes_do_item(item, n):
    """As seções do item `n`; nenhuma se ele não leva o grupo IBS/CBS."""
    if not item.get("ibs_cbs_situacao_tributaria"):
        return []
    secoes = [(f"IBSCBS{n:03d}", {
        "CST": item["ibs_cbs_situacao_tributaria"],
        "cClassTrib": item["ibs_cbs_classificacao_tributaria"],
    })]
    if "ibs_cbs_base_calculo" not in item:  # CST sem valores (ex.: 410)
        return secoes
    v_ibs = _d(item, "ibs_uf_valor") + _d(item, "ibs_mun_valor")
    secoes.append((f"gIBSCBS{n:03d}", {"vBC": item["ibs_cbs_base_calculo"], "vIBS": str(v_ibs)}))
    for secao, prefixo, chave_aliquota, chave_valor in GRUPOS:
        secoes.append((f"{secao}{n:03d}", {
            chave_aliquota: item[f"{prefixo}_aliquota"],
            chave_valor: item[f"{prefixo}_valor"],
            "pDif": item.get(f"{prefixo}_percentual_diferimento"),
            "vDif": item.get(f"{prefixo}_valor_diferido"),
            "pRedAliq": item.get(f"{prefixo}_percentual_reducao_aliquota"),
            "pAliqEfet": item.get(f"{prefixo}_aliquota_efetiva"),
        }))
    return secoes


def secoes_do_total(itens):
    """`IBSCBSTot` e seus grupos; nenhuma se nenhum item leva IBS/CBS.

    vDif e vDevTrib são obrigatórios no total mesmo zerados, por isso saem
    "0.00" em vez de ficarem de fora.
    """
    com_grupo = [item for item in itens if item.get("ibs_cbs_situacao_tributaria")]
    if not com_grupo:
        return []

    def soma(chave):
        return sum((_d(item, chave) for item in com_grupo), start=Decimal("0.00"))

    uf, mun, cbs = soma("ibs_uf_valor"), soma("ibs_mun_valor"), soma("cbs_valor")
    zero = "0.00"
    return [
        ("IBSCBSTot", {"vBCIBSCBS": str(soma("ibs_cbs_base_calculo"))}),
        ("gIBS", {"vIBS": str(uf + mun), "vCredPres": zero, "vCredPresCondSus": zero}),
        ("gIBSUFTot", {"vDif": str(soma("ibs_uf_valor_diferido")), "vDevTrib": zero, "vIBSUF": str(uf)}),
        ("gIBSMunTot", {"vDif": str(soma("ibs_mun_valor_diferido")), "vDevTrib": zero, "vIBSMun": str(mun)}),
        ("gCBSTot", {"vDif": str(soma("cbs_valor_diferido")), "vDevTrib": zero, "vCBS": str(cbs),
                     "vCredPres": zero, "vCredPresCondSus": zero}),
    ]
