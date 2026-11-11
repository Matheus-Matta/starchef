# O fixture `ambiente` vem importado do teste do provedor; o pytest o injeta
# pelo nome do parâmetro, e o ruff lê isso como redefinição.
# ruff: noqa: F811
"""IBS e CBS (reforma tributária) do perfil fiscal até o INI da ACBrLib.

Os defeitos que estes testes impedem:

* a alíquota gravada no perfil — ela muda todo ano até 2033, e o perfil
  ficaria errado no dia 1º de janeiro sem ninguém perceber;
* o grupo saindo numa loja que ainda não homologou (o flag é da loja);
* os grupos aninhados no INI, que a ACBr NÃO lê (ela lê `gIBSUF001` solta, e
  só se `gIBSCBS001` existir) — o XML sairia sem os valores, calado;
* o total calculado sobre a nota em vez de somar os itens arredondados.
"""
import configparser
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.invoices import ibs_cbs
from apps.invoices.models import FiscalProfile
from apps.invoices.providers_erros import FiscalRejection
from apps.invoices.serializers import FiscalProfileSerializer
from apps.invoices.tests.test_acbrlib_provider import Comunicador, ambiente  # noqa: F401
from apps.invoices.tests.test_acbrlib_rejeicoes_comuns import _emitir_com, _ini_emitido, _pagar

pytestmark = pytest.mark.django_db

ALIQUOTAS_2026 = ibs_cbs.ALIQUOTAS[2026]


def _item(cst="000", cclass="000001", reducao=0, diferimento=0):
    return SimpleNamespace(ibs_cbs_cst=cst, ibs_cbs_cclass_trib=cclass,
                           ibs_cbs_reducao=Decimal(reducao), ibs_cbs_diferimento=Decimal(diferimento))


# ── cálculo ───────────────────────────────────────────────────────────────────

def test_2026_e_o_ano_de_teste_cbs_0_9_e_ibs_0_1():
    assert ALIQUOTAS_2026 == (Decimal("0.10"), Decimal("0.00"), Decimal("0.90"))


def test_item_de_100_reais_paga_90_centavos_de_cbs_e_10_de_ibs():
    campos = ibs_cbs.campos_do_item(_item(), base=Decimal("100.00"), ano=2026)

    assert campos["ibs_cbs_base_calculo"] == "100.00"
    assert (campos["cbs_valor"], campos["ibs_uf_valor"], campos["ibs_mun_valor"]) == ("0.90", "0.10", "0.00")
    assert "cbs_aliquota_efetiva" not in campos  # sem redução, sem gRed


def test_reducao_de_60_por_cento_aplica_na_aliquota():
    campos = ibs_cbs.campos_do_item(_item("200", "200003", reducao=60), base=Decimal("100.00"), ano=2026)

    assert campos["cbs_aliquota_efetiva"] == "0.3600"
    assert campos["cbs_valor"] == "0.36"
    assert campos["cbs_percentual_reducao_aliquota"] == "60.0000"


def test_diferimento_tira_o_diferido_do_valor_devido():
    campos = ibs_cbs.campos_do_item(_item("510", "510001", diferimento=100), base=Decimal("100.00"), ano=2026)

    assert (campos["cbs_valor"], campos["cbs_valor_diferido"]) == ("0.00", "0.90")


def test_cst_410_leva_so_cst_e_cclasstrib():
    campos = ibs_cbs.campos_do_item(_item("410", "410001"), base=Decimal("100.00"), ano=2026)

    assert campos == {"ibs_cbs_situacao_tributaria": "410", "ibs_cbs_classificacao_tributaria": "410001"}


def test_ano_sem_aliquota_cadastrada_recusa_em_vez_de_inventar():
    with pytest.raises(FiscalRejection, match="alíquotas de referência do IBS/CBS de 2099"):
        ibs_cbs.campos_do_item(_item(), base=Decimal("10.00"), ano=2099)


# ── cadastro ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dados,campo", [
    ({"ibs_cbs_cst": "000", "ibs_cbs_cclass_trib": "200003"}, "ibs_cbs_cclass_trib"),
    ({"ibs_cbs_cst": "000", "ibs_cbs_cclass_trib": "00A001"}, "ibs_cbs_cclass_trib"),
    ({"ibs_cbs_cst": "550", "ibs_cbs_cclass_trib": "550001"}, "ibs_cbs_cst"),
    ({"ibs_cbs_cst": "000", "ibs_cbs_cclass_trib": "000001", "ibs_cbs_reducao": "60"}, "ibs_cbs_reducao"),
    ({"ibs_cbs_cst": "200", "ibs_cbs_cclass_trib": "200003", "ibs_cbs_diferimento": "10"}, "ibs_cbs_diferimento"),
    ({"ibs_cbs_reducao": "60"}, "ibs_cbs_cst"),
])
def test_perfil_com_regra_impossivel_e_recusado(dados, campo):
    serializer = FiscalProfileSerializer(data={"name": "Bebida", **dados})

    assert not serializer.is_valid()
    assert campo in serializer.errors


def test_perfil_sem_ibs_cbs_continua_valido():
    """Quem ainda não preencheu a reforma não pode ter o cadastro travado."""
    assert ibs_cbs.erros_do_perfil(cst="", cclass_trib="", reducao=0, diferimento=0) == {}


# ── INI da ACBrLib ────────────────────────────────────────────────────────────

def _com_perfil(ambiente, monkeypatch, *, ligado=True, **regra):
    monkeypatch.setitem(ibs_cbs.ALIQUOTAS, timezone.localdate().year, ALIQUOTAS_2026)
    ambiente.config.ibs_cbs_enabled = ligado
    ambiente.config.default_profile = FiscalProfile.objects.create(
        account=ambiente.config.account, name="Prato", ncm="21069090", csosn="102", **regra)
    ambiente.config.save(update_fields=["ibs_cbs_enabled", "default_profile"])
    _pagar(ambiente, "pix", "25.00")


def _ler(ini):
    leitor = configparser.ConfigParser(interpolation=None, strict=False)
    leitor.optionxform = str
    leitor.read_string(ini)
    return leitor


def test_ini_leva_os_grupos_soltos_como_a_acbr_le(ambiente, monkeypatch):
    _com_perfil(ambiente, monkeypatch, ibs_cbs_cst="000", ibs_cbs_cclass_trib="000001")

    ini = _ler(_ini_emitido(ambiente, monkeypatch))

    assert dict(ini["IBSCBS001"]) == {"CST": "000", "cClassTrib": "000001"}
    assert dict(ini["gIBSCBS001"]) == {"vBC": "25.00", "vIBS": "0.03"}
    assert dict(ini["gCBS001"]) == {"pCBS": "0.9000", "vCBS": "0.23"}
    assert dict(ini["gIBSUF001"]) == {"pIBSUF": "0.1000", "vIBSUF": "0.03"}
    assert ini["gIBSMun001"]["vIBSMun"] == "0.00"
    assert ini["IBSCBSTot"]["vBCIBSCBS"] == "25.00"
    assert (ini["gIBS"]["vIBS"], ini["gCBSTot"]["vCBS"], ini["gCBSTot"]["vDif"]) == ("0.03", "0.23", "0.00")


def test_loja_sem_o_flag_nao_manda_ibs_cbs(ambiente, monkeypatch):
    """O perfil já preenchido não muda o XML de quem ainda não homologou."""
    _com_perfil(ambiente, monkeypatch, ligado=False, ibs_cbs_cst="000", ibs_cbs_cclass_trib="000001")

    ini = _ini_emitido(ambiente, monkeypatch)

    assert "IBSCBS" not in ini and "gCBS" not in ini


def test_a_regra_e_copiada_para_o_item_da_nota(ambiente, monkeypatch):
    _com_perfil(ambiente, monkeypatch, ibs_cbs_cst="200", ibs_cbs_cclass_trib="200003", ibs_cbs_reducao=60)

    nota = _emitir_com(ambiente, monkeypatch, Comunicador("online"))

    with tenant_context(nota.account):
        item = nota.items.get()
    assert (item.ibs_cbs_cst, item.ibs_cbs_cclass_trib, item.ibs_cbs_reducao) == ("200", "200003", Decimal("60"))


def test_flag_ligado_e_perfil_sem_cst_vira_pendencia_do_cadastro(ambiente, monkeypatch):
    _com_perfil(ambiente, monkeypatch)

    nota = _emitir_com(ambiente, monkeypatch, Comunicador("online"))

    pendencias = nota.fiscal_payload["fiscal_profile_issues"]
    assert [p["field"] for p in pendencias] == ["ibs_cbs_cst"]


# ── sincronização ─────────────────────────────────────────────────────────────

def test_regra_e_flag_viajam_para_a_loja():
    """Campo novo não tem trava automática: a loja emite com o que recebe."""
    from apps.synchronization.services import serialization
    from apps.synchronization.services.registry import registry

    por_modelo = {e.model_label: e for e in registry.entries.values()}
    for modelo, campos in {
        "invoices.FiscalProfile": ibs_cbs_campos(),
        "invoices.FiscalConfig": {"ibs_cbs_enabled"},
        "invoices.InvoiceItem": ibs_cbs_campos(),
    }.items():
        entrada = por_modelo[modelo]
        assert campos <= set(serialization.serialize(entrada.model(), entrada)), modelo


def ibs_cbs_campos():
    from apps.invoices.models_ibs_cbs import CAMPOS

    return set(CAMPOS)
