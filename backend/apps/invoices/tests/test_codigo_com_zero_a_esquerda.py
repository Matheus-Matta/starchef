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
