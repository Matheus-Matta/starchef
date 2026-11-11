"""IBS e CBS da reforma tributária (NT 2025.002-RTC): regra e cálculo por item.

O perfil fiscal guarda a REGRA (CST, cClassTrib, redução, diferimento), nunca
o valor: a alíquota vem da tabela do ano da emissão (`ALIQUOTAS`), porque ela
muda todo ano até 2033 e gravá-la em cada perfil deixaria todos errados no dia
1º de janeiro.

O CST e o cClassTrib são um par só para os dois tributos; as alíquotas e os
valores são três: IBS estadual, IBS municipal e CBS.

As chaves que este módulo devolve são as da API da Focus (o documento neutro
nasceu no formato dela, ver `documento.py`); a ACBrLib as traduz para o INI em
`acbrlib/ini_ibs_cbs.py`.
"""
from collections import namedtuple
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from apps.invoices.providers_erros import FiscalRejection

CENTAVO = Decimal("0.01")
QUATRO_CASAS = Decimal("0.0001")
CEM = Decimal("100")

Aliquotas = namedtuple("Aliquotas", "ibs_uf ibs_mun cbs")

#: Alíquotas de referência por ano, em %. 2026 é o ano de teste (LC 214/2025,
#: art. 343): CBS 0,9% e IBS 0,1%, todo ele estadual. Ano que falta aqui
#: RECUSA a nota, de propósito: inventar uma alíquota produziria um documento
#: aceito e errado. Cadastrar o ano seguinte é tarefa de dezembro.
ALIQUOTAS = {
    2026: Aliquotas(ibs_uf=Decimal("0.10"), ibs_mun=Decimal("0.00"), cbs=Decimal("0.90")),
}

#: Os CST que o StarChef sabe montar. Os demais (550, 620, 800...) exigem
#: grupos que uma venda de restaurante não tem (tributação regular,
#: monofásica, transferência de crédito) e são recusados no cadastro, em vez
#: de saírem pela metade na nota.
CST = {
    "000": "Tributação integral",
    "200": "Alíquota reduzida",
    "410": "Imunidade e não incidência",
    "510": "Diferimento",
    "515": "Diferimento com redução de alíquota",
}
#: Sem o grupo de valores (gIBSCBS): a nota leva só o CST e o cClassTrib.
CST_SEM_VALOR = {"410"}
CST_COM_REDUCAO = {"200", "515"}
CST_COM_DIFERIMENTO = {"510", "515"}

#: Os três tributos, na ordem do XML: prefixo da chave da Focus.
TRIBUTOS = ("ibs_uf", "ibs_mun", "cbs")


def completar_zeros(valor, tamanho):
    """Devolve o zero à esquerda que o Excel apagou: "1" → "000001".

    Reimportar a planilha exportada é o caminho comum, e o Excel lê CST e
    cClassTrib como número. Só vale para dígitos MAIS CURTOS que o código:
    como o código é todo numérico e de tamanho fixo, isso é exatamente o que
    se perdeu, e não um palpite.
    """
    valor = str(valor or "").strip()
    return valor.zfill(tamanho) if valor.isdigit() and len(valor) < tamanho else valor


def erros_do_perfil(*, cst, cclass_trib, reducao, diferimento):
    """O que torna a regra impossível de montar. Devolve `{campo: mensagem}`.

    Fonte única do serializer e do admin. Redução e diferimento só cabem no
    CST que os prevê: um percentual de redução num CST 000 seria ignorado pela
    SEFAZ e daria a impressão de que o produto paga menos.
    """
    erros = {}
    reducao, diferimento = Decimal(reducao or 0), Decimal(diferimento or 0)
    if not cst and not cclass_trib:
        if reducao or diferimento:
            erros["ibs_cbs_cst"] = "Informe o CST do IBS/CBS antes da redução ou do diferimento."
        return erros
    if cst not in CST:
        erros["ibs_cbs_cst"] = (
            f"CST {cst or '(vazio)'} não é suportado. Use um destes: " + ", ".join(CST) + "."
        )
    if not (len(cclass_trib or "") == 6 and cclass_trib.isdigit()):
        erros["ibs_cbs_cclass_trib"] = "cClassTrib tem 6 dígitos (ex.: 000001)."
    elif cst and not cclass_trib.startswith(cst):
        # Na tabela oficial o cClassTrib começa pelo CST a que pertence.
        erros["ibs_cbs_cclass_trib"] = f"cClassTrib {cclass_trib} não pertence ao CST {cst}."
    if reducao and cst not in CST_COM_REDUCAO:
        erros["ibs_cbs_reducao"] = "Redução de alíquota só vale nos CST 200 e 515."
    if diferimento and cst not in CST_COM_DIFERIMENTO:
        erros["ibs_cbs_diferimento"] = "Diferimento só vale nos CST 510 e 515."
    if not Decimal("0") <= reducao <= CEM:
        erros["ibs_cbs_reducao"] = "A redução é um percentual entre 0 e 100."
    if not Decimal("0") <= diferimento <= CEM:
        erros["ibs_cbs_diferimento"] = "O diferimento é um percentual entre 0 e 100."
    return erros


def aliquotas_do_ano(ano, *, rotulo="Emissor"):
    try:
        return ALIQUOTAS[ano]
    except KeyError:
        raise FiscalRejection(
            f"{rotulo}: as alíquotas de referência do IBS/CBS de {ano} não estão "
            "cadastradas no StarChef (apps/invoices/ibs_cbs.py)."
        ) from None


def ano_da_emissao(data_emissao):
    if isinstance(data_emissao, datetime):
        return data_emissao.year
    if data_emissao:
        return datetime.fromisoformat(str(data_emissao)).year
    from django.utils import timezone

    return timezone.localdate().year


def _tributo(prefixo, *, base, aliquota, reducao, diferimento):
    efetiva = (aliquota * (CEM - reducao) / CEM).quantize(QUATRO_CASAS, rounding=ROUND_HALF_UP)
    bruto = (base * efetiva / CEM).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    diferido = (bruto * diferimento / CEM).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    campos = {
        f"{prefixo}_aliquota": str(aliquota.quantize(QUATRO_CASAS)),
        f"{prefixo}_valor": str(bruto - diferido),
    }
    if reducao:
        campos[f"{prefixo}_percentual_reducao_aliquota"] = str(reducao.quantize(QUATRO_CASAS))
        campos[f"{prefixo}_aliquota_efetiva"] = str(efetiva)
    if diferimento:
        campos[f"{prefixo}_percentual_diferimento"] = str(diferimento.quantize(QUATRO_CASAS))
        campos[f"{prefixo}_valor_diferido"] = str(diferido)
    return campos


def campos_do_item(item, *, base, ano, rotulo="Emissor"):
    """Os campos de IBS/CBS de um item da nota, já calculados.

    `base` é o valor do item depois do rateio: produto - desconto + outras
    despesas. Cada valor é arredondado no item, e o total da nota é a soma
    desses valores arredondados — não o percentual sobre o total.
    """
    campos = {
        "ibs_cbs_situacao_tributaria": item.ibs_cbs_cst,
        "ibs_cbs_classificacao_tributaria": item.ibs_cbs_cclass_trib,
    }
    if item.ibs_cbs_cst in CST_SEM_VALOR:
        return campos
    aliquotas = aliquotas_do_ano(ano, rotulo=rotulo)
    base = Decimal(base).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    campos["ibs_cbs_base_calculo"] = str(base)
    for prefixo in TRIBUTOS:
        campos.update(_tributo(
            prefixo, base=base, aliquota=getattr(aliquotas, prefixo),
            reducao=Decimal(item.ibs_cbs_reducao or 0),
            diferimento=Decimal(item.ibs_cbs_diferimento or 0),
        ))
    return campos


def pendencias(perfil, *, prefixo="", subject=""):
    """O que falta no perfil para a nota levar o grupo IBS/CBS."""
    if getattr(perfil, "ibs_cbs_cst", "") and getattr(perfil, "ibs_cbs_cclass_trib", ""):
        return []
    return [{
        "field": "ibs_cbs_cst", "label": "CST do IBS/CBS",
        "message": f"{prefixo}CST e cClassTrib do IBS/CBS não informados.", "subject": subject,
    }]
