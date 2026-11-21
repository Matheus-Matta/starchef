"""O comunicador completa os totais que o backend antigo não mandava.

Produção, 20/11/2026: "602 Rejeicao: Total do PIS difere do somatorio dos
itens sujeitos ao ICMS". A loja atualizou só o comunicador; o backend dela
ainda mandava a `[Total]` sem vBC/vICMS/vPIS/vCOFINS.
"""
from app.totais import completar_totais

INI_DO_BACKEND_ANTIGO = """[Produto001]
vProd=50.00
[ICMS001]
orig=0
CST=00
vBC=50.00
pICMS=12.00
vICMS=6.00
[PIS001]
CST=01
vPIS=0.33
vBC=50.00
pPIS=0.65
[COFINS001]
CST=01
vCOFINS=1.50
[Produto002]
vProd=10.00
[ICMS002]
orig=0
CST=60
vBC=10.00
pICMS=12.00
vICMS=1.20
[PIS002]
CST=04
vPIS=0.00
[COFINS002]
CST=04
vCOFINS=0.00
[Total]
vProd=60.00
vNF=60.00

[pag001]
tPag=01
"""


def _total(texto):
    return texto.split("[Total]")[1].split("[pag001]")[0]


def test_total_do_pis_e_do_cofins_e_a_soma_dos_itens():
    total = _total(completar_totais(INI_DO_BACKEND_ANTIGO))

    assert "vPIS=0.33" in total and "vCOFINS=1.50" in total


def test_icms_do_cst_60_fica_fora_do_total():
    total = _total(completar_totais(INI_DO_BACKEND_ANTIGO))

    assert "vBC=50.00" in total and "vICMS=6.00" in total


def test_total_que_o_backend_mandou_e_a_autoridade():
    ini = INI_DO_BACKEND_ANTIGO.replace("vNF=60.00", "vNF=60.00\nvPIS=0.40")

    total = _total(completar_totais(ini))

    assert "vPIS=0.40" in total and "vPIS=0.33" not in total
    assert total.count("vPIS=") == 1


def test_o_resto_do_ini_nao_muda():
    texto = completar_totais(INI_DO_BACKEND_ANTIGO)

    assert "vProd=60.00" in texto and "[pag001]\ntPag=01" in texto


def test_pis_e_cofins_monofasico_ficam_fora_do_total():
    """21/11/2026: CST 04 com valor no INI — a lib descarta no item; o total também."""
    texto = completar_totais("[PIS001]\nCST=04\nvPIS=0.10\n[COFINS001]\nCST=4\nvCOFINS=0.46\n"
                             "[PIS002]\nCST=01\nvPIS=0.33\n[Total]\nvNF=10.00\n")

    assert "vPIS=0.33" in texto and "vCOFINS=0.00" in texto
