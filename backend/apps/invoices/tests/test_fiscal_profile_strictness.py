"""Cadastro fiscal incompleto para de sair escondido dentro do payload.

Os defaults de `_build_item` (`00000000`, `5102`, `102`, `49`) eram aplicados na
transmissao, depois de o cliente ja ter pago e longe de quem podia corrigir.
Aqui se garante que:

* CSOSN e CST sao escolhidos pelo REGIME, nao pelo que estiver preenchido;
* uma empresa em regime normal sem CST falha com mensagem clara, sempre;
* com `strict_fiscal_profile` desligado a emissao segue, mas o que faltava fica
  registrado na nota e na auditoria;
* com o flag ligado a nota nem chega ao provedor.
"""
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from apps.invoices.fiscal import fiscal_profile_issues
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice
from apps.invoices.providers import FocusNfeProvider
from apps.invoices.services import emit_fiscal_invoice, fiscal_readiness, resend_fiscal_invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


def _fake_authorized():
    response = Mock()
    response.status_code = 200
    response.content = b"{}"
    response.json.return_value = {
        "status": "autorizado",
        "chave_nfe": "NFe35" + "0" * 42,
        "protocolo": "135260000000001",
    }
    response.text = ""
    return response


def _profile(account, **fields):
    defaults = {
        "name": f"Perfil {uuid.uuid4().hex[:6]}",
        "ncm": "19059090",
        "cfop": "5102",
        "csosn": "102",
    }
    return FiscalProfile.objects.create(account=account, **{**defaults, **fields})


def _product(account, restaurant, branch, profile=None):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"), fiscal_profile=profile,
    )


def _config(account, restaurant, branch, **fields):
    account_config = account.focus_nfe_config
    account_config.homologation_url = "https://homologacao.focusnfe.com.br"
    account_config.save(update_fields=["homologation_url", "updated_at"])
    defaults = {
        "provider": FocusNfeProvider.name,
        "focus_token_homologation": "fake-token",
        "cnpj": "11222333000181",
        "uf": "SP",
        "environment": FiscalConfig.ENV_HOMOLOGATION,
        "series": 1,
        "next_number": 1,
        # Cadastro completo do emitente: o reenvio recusa antes de tentar
        # quando falta algo aqui, e o recorte destes testes e o do PRODUTO.
        "corporate_name": "Loja Teste LTDA",
        "ie": "123456789",
        "address_line": "Rua Central",
        "address_number": "100",
        "district": "Centro",
        "city": "Sao Paulo",
        "city_ibge": "3550308",
        "zip_code": "01001000",
        "csc_id": "000001",
        "csc_token": "ABC123",
    }
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, **{**defaults, **fields}
    )


def _order(restaurant, branch, product, user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user)
    add_order_item(order=order, product=product, quantity=1, user=user)
    return order


# ----------------------------------------------------------------- regime

@patch("requests.post")
def test_simples_sends_csosn(mock_post, account, restaurant, branch, manager_user):
    mock_post.return_value = _fake_authorized()
    product = _product(account, restaurant, branch, _profile(account, csosn="102", cst_icms=""))
    _config(account, restaurant, branch, crt=FiscalConfig.CRT_SIMPLES)

    emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)

    item = mock_post.call_args.kwargs["json"]["items"][0]
    assert item["icms_situacao_tributaria"] == "102"


@patch("requests.post")
def test_regime_normal_sends_cst_not_csosn(mock_post, account, restaurant, branch, manager_user):
    """Um perfil com os dois preenchidos nao pode mandar o do regime errado."""
    mock_post.return_value = _fake_authorized()
    product = _product(account, restaurant, branch, _profile(account, csosn="102", cst_icms="00"))
    _config(account, restaurant, branch, crt=FiscalConfig.CRT_NORMAL)

    emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)

    item = mock_post.call_args.kwargs["json"]["items"][0]
    assert item["icms_situacao_tributaria"] == "00"


@patch("requests.post")
def test_regime_normal_without_cst_fails_even_with_strict_off(
    mock_post, account, restaurant, branch, manager_user
):
    """Nao existe CST padrao seguro: adivinhar um geraria nota aceita e errada.

    O comportamento antigo mandava CSOSN 102 aqui — que so existe no Simples e
    seria recusado de qualquer forma. Falhar com mensagem clara e estritamente
    melhor, entao nao depende do flag.
    """
    mock_post.return_value = _fake_authorized()
    product = _product(account, restaurant, branch, _profile(account, csosn="", cst_icms=""))
    _config(
        account, restaurant, branch,
        crt=FiscalConfig.CRT_NORMAL, strict_fiscal_profile=False,
    )

    invoice = emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)

    assert invoice.status == Invoice.STATUS_ERROR
    assert "CST do ICMS" in invoice.error_message
    assert mock_post.call_count == 0


# ------------------------------------------------------------------- flag

@patch("requests.post")
def test_incomplete_profile_still_emits_but_is_recorded(
    mock_post, account, restaurant, branch, manager_user
):
    """Flag desligado: a emissao segue, mas a dependencia do padrao fica visivel.

    E isso que permite descobrir quem ainda depende dos valores padrao antes de
    virar a chave, em vez de quebrar todo mundo num deploy.
    """
    mock_post.return_value = _fake_authorized()
    product = _product(account, restaurant, branch, _profile(account, ncm=""))
    _config(account, restaurant, branch, strict_fiscal_profile=False)

    invoice = emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)

    assert invoice.status == Invoice.STATUS_ISSUED
    issues = invoice.fiscal_payload["fiscal_profile_issues"]
    assert [issue["field"] for issue in issues] == ["ncm"]
    assert issues[0]["line_number"] == 1
    # E o padrao continuou sendo aplicado na transmissao, como antes.
    assert mock_post.call_args.kwargs["json"]["items"][0]["codigo_ncm"] == "00000000"


@patch("requests.post")
def test_strict_refuses_before_reaching_the_provider(
    mock_post, account, restaurant, branch, manager_user
):
    product = _product(account, restaurant, branch, _profile(account, ncm=""))
    _config(account, restaurant, branch, strict_fiscal_profile=True)

    invoice = emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)

    assert invoice.status == Invoice.STATUS_ERROR
    assert "NCM nao informado" in invoice.error_message
    assert invoice.fiscal_payload["failure"] == "rejection"
    assert mock_post.call_count == 0


@patch("requests.post")
def test_strict_with_complete_profile_emits_normally(
    mock_post, account, restaurant, branch, manager_user
):
    mock_post.return_value = _fake_authorized()
    product = _product(account, restaurant, branch, _profile(account))
    _config(account, restaurant, branch, strict_fiscal_profile=True)

    invoice = emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)

    assert invoice.status == Invoice.STATUS_ISSUED
    assert "fiscal_profile_issues" not in invoice.fiscal_payload


def test_product_without_profile_is_reported_not_defaulted(account):
    issues = fiscal_profile_issues(None, crt=FiscalConfig.CRT_SIMPLES, subject="Refrigerante")

    assert [issue["field"] for issue in issues] == ["fiscal_profile"]
    assert "Refrigerante" in issues[0]["message"]


# -------------------------------------------------------------- pre-voo

def test_readiness_lists_the_products_that_block_the_shift(
    account, restaurant, branch, manager_user
):
    config = _config(account, restaurant, branch)
    _product(account, restaurant, branch, _profile(account))
    broken = _product(account, restaurant, branch, None)

    report = fiscal_readiness(config)

    assert report["ready"] is False
    assert report["products_checked"] == 2
    assert report["products_with_issues"] == 1
    assert report["products"][0]["product"] == str(broken.id)
    assert report["strict"] is False


def test_readiness_is_clean_when_every_product_has_a_complete_profile(
    account, restaurant, branch, manager_user
):
    profile = _profile(account)
    config = _config(account, restaurant, branch)
    _product(account, restaurant, branch, profile)

    report = fiscal_readiness(config)

    assert report["products_with_issues"] == 0
    # `ready` tambem depende do cadastro do emitente, que neste teste esta
    # propositalmente minimo — o que importa aqui e a metade dos produtos.
    assert report["products"] == []


def test_readiness_falls_back_to_the_default_profile_of_the_config(
    account, restaurant, branch, manager_user
):
    """Produto sem perfil proprio nao e pendencia se a config tem padrao."""
    config = _config(account, restaurant, branch, default_profile=_profile(account))
    _product(account, restaurant, branch, None)

    report = fiscal_readiness(config)

    assert report["products_with_issues"] == 0


def test_readiness_endpoint_answers_before_the_first_sale(
    account, restaurant, branch, api_client
):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    _config(account, restaurant, branch)
    _product(account, restaurant, branch, None)

    response = api_client.get(
        "/api/v1/fiscal/config/readiness/", {"restaurant": str(restaurant.id)}
    )

    assert response.status_code == 200, response.data
    assert response.data["ready"] is False
    assert response.data["products_with_issues"] == 1
    assert response.data["products"][0]["issues"][0]["field"] == "fiscal_profile"


# ------------------------------------------------------ reenvio depois da correcao

@patch("requests.post")
def test_resend_uses_the_corrected_profile_not_the_frozen_one(
    mock_post, account, restaurant, branch, manager_user
):
    """Corrigir o cadastro e reenviar precisa funcionar.

    O `InvoiceItem` e um retrato congelado, entao o reenvio repetia o NCM vazio
    da emissao e mandava `00000000` de novo — a correcao do operador nao tinha
    efeito nenhum. Uma nota que nunca foi transmitida nao e documento: o retrato
    dela pode ser refeito com o cadastro de agora.
    """
    mock_post.return_value = _fake_authorized()
    profile = _profile(account, ncm="")
    product = _product(account, restaurant, branch, profile)
    _config(account, restaurant, branch, strict_fiscal_profile=True)
    invoice = emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)
    assert invoice.status == Invoice.STATUS_ERROR

    profile.ncm = "19059090"
    profile.save(update_fields=["ncm"])

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.status == Invoice.STATUS_ISSUED
    assert mock_post.call_args.kwargs["json"]["items"][0]["codigo_ncm"] == "19059090"
    assert "fiscal_profile_issues" not in resent.fiscal_payload


@patch("requests.post")
def test_resend_still_blocked_while_the_cadastro_is_incomplete(
    mock_post, account, restaurant, branch, manager_user
):
    """O flag vale nas DUAS portas.

    Antes, `strict_fiscal_profile` era checado so na emissao: o reenvio passava
    por cima e transmitia o item incompleto assim mesmo.
    """
    product = _product(account, restaurant, branch, _profile(account, ncm=""))
    _config(account, restaurant, branch, strict_fiscal_profile=True)
    invoice = emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.status == Invoice.STATUS_ERROR
    assert "NCM nao informado" in resent.error_message
    assert mock_post.call_count == 0


@patch("requests.post")
def test_resend_without_strict_records_the_pending_issue_again(
    mock_post, account, restaurant, branch, manager_user
):
    """Com o flag desligado o reenvio sai, mas a pendencia continua registrada."""
    mock_post.return_value = _fake_authorized()
    product = _product(account, restaurant, branch, _profile(account, ncm=""))
    _config(account, restaurant, branch, strict_fiscal_profile=False)
    invoice = emit_fiscal_invoice(_order(restaurant, branch, product, manager_user), user=manager_user)
    invoice.status = Invoice.STATUS_ERROR
    invoice.save(update_fields=["status", "updated_at"])

    resent = resend_fiscal_invoice(invoice, user=manager_user)

    assert resent.status == Invoice.STATUS_ISSUED
    assert resent.fiscal_payload["fiscal_profile_issues"][0]["field"] == "ncm"
