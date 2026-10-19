# O fixture `ambiente` vem importado do teste do provedor; o pytest o injeta
# pelo nome do parâmetro, e o ruff lê isso como redefinição.
# ruff: noqa: F811
"""As recusas que continuavam voltando na loja, mesmo depois de "resolvidas".

**866 (troco).** O INI levava o `vTroco` numa seção `[pag]` à parte. A
ACBrLib lê o troco DENTRO de cada `[pagNNN]` (`ACBrNFe.IniReader.pas`,
`Ler_Pagamento`) e ignorava o nosso: toda venda com troco saía sem `vTroco`.
O teste antigo só procurava `vTroco=` em qualquer lugar do arquivo — aqui o
INI é lido como a ACBr lê.

**386 (CFOP × CSOSN).** Produto do Simples com CSOSN 500 e CFOP 5102 (ou 102
com 5405) é recusado sempre, e reenviar repetia o mesmo par.

**613 / numeração.** Emitir de novo uma nota recusada dava a ela NÚMERO e cNF
novos: buraco na série a cada tentativa, e a nota deixava de se reconhecer se
uma tentativa anterior tinha sido autorizada.
"""
import configparser
from types import SimpleNamespace

import pytest

from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice
from apps.invoices.tests.test_acbrlib_provider import Comunicador, ambiente  # noqa: F401
from apps.invoices.tests.test_acbrlib_rejeicoes_comuns import (
    CNF_DE_OUTRO_EMISSOR,
    SefazComNumeroUsado,
    _campo,
    _emitir_com,
    _ini_emitido,
    _pagar,
)

pytestmark = pytest.mark.django_db


def como_a_acbr_le(ini):
    """O INI lido como o `TNFeIniReader`: seções e chaves sem caixa."""
    leitor = configparser.ConfigParser(interpolation=None, strict=False)
    leitor.read_string(ini)
    pagamentos, troco, n = [], None, 1
    while leitor.has_section(f"pag{n:03d}") and leitor[f"pag{n:03d}"].get("tpag"):
        secao = leitor[f"pag{n:03d}"]
        pagamentos.append(secao.get("vpag"))
        if float(secao.get("vtroco") or 0) > 0:
            troco = secao.get("vtroco")
        n += 1
    produtos, n = [], 1
    while leitor.has_section(f"Produto{n:03d}"):
        produtos.append(SimpleNamespace(cfop=leitor[f"Produto{n:03d}"].get("cfop"),
                                        csosn=leitor[f"ICMS{n:03d}"].get("csosn")))
        n += 1
    return SimpleNamespace(pagamentos=pagamentos, troco=troco, produtos=produtos)


# ── 866 ───────────────────────────────────────────────────────────────────────

def test_troco_do_dinheiro_chega_a_acbr(ambiente, monkeypatch):
    """Cliente deu R$ 30 numa conta de R$ 25: a ACBr precisa LER vTroco=5,00."""
    _pagar(ambiente, "cash", "25.00", troco="5.00")

    lido = como_a_acbr_le(_ini_emitido(ambiente, monkeypatch))

    assert lido.pagamentos == ["30.00"]
    assert lido.troco == "5.00"


def test_troco_com_duas_formas_chega_a_acbr(ambiente, monkeypatch):
    _pagar(ambiente, "cash", "20.00", troco="5.00")
    _pagar(ambiente, "pix", "5.00")

    assert como_a_acbr_le(_ini_emitido(ambiente, monkeypatch)).troco == "5.00"


def test_sem_troco_a_acbr_nao_le_troco_nenhum(ambiente, monkeypatch):
    _pagar(ambiente, "pix", "25.00")

    assert como_a_acbr_le(_ini_emitido(ambiente, monkeypatch)).troco is None


# ── 386 ───────────────────────────────────────────────────────────────────────

def _perfil(ambiente, *, cfop, csosn):
    ambiente.config.crt = FiscalConfig.CRT_SIMPLES
    ambiente.config.default_profile = FiscalProfile.objects.create(
        account=ambiente.config.account, name=f"{csosn}/{cfop}", ncm="21069090",
        cfop=cfop, csosn=csosn)
    ambiente.config.save(update_fields=["crt", "default_profile"])


@pytest.mark.parametrize("cfop,csosn,esperado", [
    ("5102", "500", "5405"),   # ST já recolhida: venda é 5405
    ("5405", "102", "5102"),   # tributada no Simples: venda é 5102
    ("5405", "900", "5102"),   # o caso da OOBJ: 900 com 5405 é a 386
    ("5656", "500", "5656"),   # par aceito fica como está
    ("5102", "102", "5102"),
])
def test_cfop_que_nao_combina_com_o_csosn_e_ajustado(ambiente, monkeypatch, cfop, csosn, esperado):
    _perfil(ambiente, cfop=cfop, csosn=csosn)
    _pagar(ambiente, "pix", "25.00")

    produto = como_a_acbr_le(_ini_emitido(ambiente, monkeypatch)).produtos[0]

    assert (produto.csosn, produto.cfop) == (csosn, esperado)


# ── numeração da nota emitida de novo ─────────────────────────────────────────

def test_emitir_de_novo_a_nota_recusada_reaproveita_numero_e_cnf(ambiente, monkeypatch):
    """Recusa não gasta o número na SEFAZ. Antes: 1 recusada, 2 na tentativa
    seguinte, 3 na outra — buraco na série e cNF trocado a cada vez."""
    _pagar(ambiente, "pix", "25.00")
    recusa = Comunicador("recusa")
    primeira = _emitir_com(ambiente, monkeypatch, recusa)
    assert primeira.status == Invoice.STATUS_ERROR

    online = Comunicador("online")
    segunda = _emitir_com(ambiente, monkeypatch, online)

    assert segunda.status == Invoice.STATUS_ISSUED
    assert _campo(online.chamadas[0][1]["ini"], "nNF") == _campo(recusa.chamadas[0][1]["ini"], "nNF") == "1"
    assert _campo(online.chamadas[0][1]["ini"], "cNF") == _campo(recusa.chamadas[0][1]["ini"], "cNF")
    ambiente.config.refresh_from_db()
    assert ambiente.config.next_number == 2


class SefazComVariosNumerosUsados(SefazComNumeroUsado):
    """O contador ficou para trás: os `quantos` primeiros números já são de outro emissor."""

    def __init__(self, quantos):
        super().__init__(cnf=CNF_DE_OUTRO_EMISSOR, recusar_sempre=True)
        self.quantos = quantos

    def __call__(self, metodo, url, json=None, headers=None, timeout=None):
        emissoes = [c for c in self.chamadas if c[0] == "/v1/nfe/emitir"]
        self.recusar_sempre = len(emissoes) < self.quantos
        if url.endswith("/v1/nfe/emitir") and not self.recusar_sempre:
            self.chamadas.append(("/v1/nfe/emitir", json))
            return Comunicador("online")(metodo, url, json=json, headers=headers, timeout=timeout)
        return super().__call__(metodo, url, json=json, headers=headers, timeout=timeout)


def test_contador_atrasado_anda_ate_o_numero_livre(ambiente, monkeypatch):
    """Antes andava UM número por tentativa: com o contador três atrás, eram
    várias recusas 613 seguidas e o operador reenviando sem entender."""
    _pagar(ambiente, "pix", "25.00")
    sefaz = SefazComVariosNumerosUsados(quantos=3)

    nota = _emitir_com(ambiente, monkeypatch, sefaz)

    assert nota.status == Invoice.STATUS_ISSUED
    assert nota.number == "4"
    ambiente.config.refresh_from_db()
    assert ambiente.config.next_number == 5
