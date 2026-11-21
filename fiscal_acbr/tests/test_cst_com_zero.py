"""O comunicador devolve ao CST o zero que o Excel apagou.

Produção, 20/11/2026: "ACBrLib: Valor string inválido para TCSTPIS: 4". A lib
recusa a nota inteira por um zero, e o comunicador atende qualquer backend —
inclusive o de uma loja que ainda não atualizou.
"""
from app.ini import completar_codigos

INI = """[Produto001]
cProd=1
[ICMS001]
orig=0
CST=0
[PIS001]
CST=4
vPIS=0
[COFINS001]
CST=1
[ICMSTot]
vBC=10
[gIBSCBS001]
CST=000
"""


def test_cst_do_pis_cofins_e_icms_ganha_o_zero():
    texto = completar_codigos(INI)

    assert "[ICMS001]\norig=0\nCST=00" in texto
    assert "[PIS001]\nCST=04" in texto
    assert "[COFINS001]\nCST=01" in texto


def test_o_resto_do_ini_nao_muda():
    texto = completar_codigos(INI)

    assert "orig=0" in texto and "vPIS=0" in texto and "vBC=10" in texto
    assert "[gIBSCBS001]\nCST=000" in texto


def test_csosn_tem_tres_digitos_e_codigo_certo_fica_como_esta():
    texto = completar_codigos("[ICMS001]\nCSOSN=5\n[PIS001]\nCST=49\n")

    assert "CSOSN=005" in texto and "CST=49" in texto


def test_cest_e_ncm_ganham_o_zero():
    """21/11/2026: "CEST '300504' ... pattern [0-9]{7}" — o 03.005.04 do Excel."""
    texto = completar_codigos("[Produto001]\ncProd=1\nNCM=9012100\nCEST=300504\n")

    assert "NCM=09012100" in texto and "CEST=0300504" in texto and "cProd=1" in texto
