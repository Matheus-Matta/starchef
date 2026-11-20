"""O CST sai com o zero à esquerda que o Excel apagou.

Produção, 20/11/2026, regime normal: "ACBrLib: Valor string inválido para
TCSTPIS: 4". A planilha de perfis passou pelo Excel, que leu o CST "04" como o
número 4. A nota precisa do código com 2 dígitos (CST do ICMS "00", não "0").
"""
from unittest.mock import patch

import pytest

from apps.invoices.models import FiscalConfig, FiscalProfile
from apps.invoices.serializers import FiscalProfileSerializer
from apps.invoices.services import emit_fiscal_invoice
from apps.invoices.tests.test_acbrlib_provider import ambiente  # noqa: F401
from apps.invoices.tests.test_fiscal_profile_strictness import (
    _config,
    _fake_authorized,
    _order,
    _product,
    _profile,
)

pytestmark = pytest.mark.django_db


@patch("requests.post")
def test_perfil_gravado_sem_o_zero_emite_com_o_zero(mock_post, account, restaurant, branch, manager_user):
    """O perfil importado ANTES da correção emite sem precisar reimportar."""
    mock_post.return_value = _fake_authorized()
    perfil = _profile(account, csosn="", cst_icms="0", icms_rate=12,
                      pis_cst="4", cofins_cst="4")
    _config(account, restaurant, branch, crt=FiscalConfig.CRT_NORMAL)

    emit_fiscal_invoice(_order(restaurant, branch, _product(account, restaurant, branch, perfil),
                               manager_user), user=manager_user)

    item = mock_post.call_args.kwargs["json"]["items"][0]
    assert item["icms_situacao_tributaria"] == "00"
    assert item["pis_situacao_tributaria"] == "04"
    assert item["cofins_situacao_tributaria"] == "04"


def test_importar_a_planilha_grava_o_codigo_completo(account):
    dados = {"name": "REFRIGERANTE_LATA_ST", "ncm": "22021000", "cfop": "5405",
             "cst_icms": "0", "pis_cst": "4", "cofins_cst": "1", "csosn": "",
             "ibs_cbs_cst": "0", "ibs_cbs_cclass_trib": "1"}
    serializer = FiscalProfileSerializer(data=dados)
    serializer.is_valid(raise_exception=True)

    perfil = FiscalProfile(account=account, **serializer.validated_data)
    assert (perfil.cst_icms, perfil.pis_cst, perfil.cofins_cst) == ("00", "04", "01")
    assert (perfil.ibs_cbs_cst, perfil.ibs_cbs_cclass_trib) == ("000", "000001")


def test_ini_da_acbrlib_leva_o_cst_com_dois_digitos(ambiente, monkeypatch):  # noqa: F811
    """O caminho inteiro até o comunicador: perfil com "4" → INI com CST=04."""
    from apps.invoices.models import FiscalProfile as Perfil
    from apps.invoices.tests.test_acbrlib_provider import Comunicador
    from apps.orders.models import OrderItem

    perfil = Perfil.objects.create(account=ambiente.pedido.account, name="REFRI", ncm="22021000",
                                   cfop="5405", cst_icms="60", pis_cst="4", cofins_cst="4")
    produto = OrderItem.all_objects.filter(order=ambiente.pedido).first().product
    produto.fiscal_profile = perfil
    produto.save(update_fields=["fiscal_profile"])
    ambiente.config.crt = FiscalConfig.CRT_NORMAL
    ambiente.config.save(update_fields=["crt"])
    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)

    emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)

    ini = comunicador.chamadas[0][1]["ini"]
    assert "[PIS001]\nCST=04" in ini and "[COFINS001]\nCST=04" in ini


def test_migracao_corrige_o_perfil_ja_gravado_sem_o_zero(account):
    from importlib import import_module

    from django.apps import apps as registro

    perfil = _profile(account, cst_icms="0", pis_cst="4", cofins_cst="1", csosn="5")
    import_module("apps.invoices.migrations.0017_cst_com_zero_a_esquerda").completar(registro, None)

    perfil.refresh_from_db()
    assert (perfil.cst_icms, perfil.pis_cst, perfil.cofins_cst, perfil.csosn) == ("00", "04", "01", "005")
