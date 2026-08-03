"""Testa o `FocusNfeProvider` com HTTP mockado.

Isso NAO valida contra a API real do Focus NFe (sem conta/credencial pra
isso) — so garante que a logica interna (payload montado, resposta
interpretada) e consistente. Ver o docstring de `FocusNfeProvider` sobre
validar contra uma conta de homologacao real antes de ir pra producao.
"""
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FocusNfeProvider
from apps.invoices.services import emit_fiscal_invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


def _make_product(account, restaurant, branch):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
    )


def _make_fiscal_config(account, restaurant, branch):
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=FocusNfeProvider.name, provider_token="fake-token",
        cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
    )


def _order_with_item(restaurant, branch, product, user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user)
    add_order_item(order=order, product=product, quantity=1, user=user)
    return order


def _fake_response(status_code, payload):
    response = Mock()
    response.status_code = status_code
    response.content = b"{}"
    response.json.return_value = payload
    response.text = str(payload)
    return response


@patch("requests.post")
def test_authorized_response_marks_issued(mock_post, account, restaurant, branch, manager_user):
    mock_post.return_value = _fake_response(200, {
        "status": "autorizado",
        "chave_nfe": "35" + "0" * 42,
        "protocolo": "135250000000001",
        "caminho_xml_nota_fiscal": "https://focusnfe.com.br/xml/abc",
        "caminho_danfe": "https://focusnfe.com.br/danfe/abc",
    })
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch)
    order = _order_with_item(restaurant, branch, product, manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)

    assert invoice.status == Invoice.STATUS_ISSUED
    assert invoice.emission_type == Invoice.EMISSION_NORMAL
    assert invoice.authorization_protocol == "135250000000001"
    assert mock_post.call_count == 1
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["cnpj_emitente"] == "11222333000181"
    assert len(sent_payload["items"]) == 1
    assert sent_payload["items"][0]["descricao"] == "X-Burger"


@patch("requests.post")
def test_processing_response_stays_pending_without_contingency(mock_post, account, restaurant, branch, manager_user):
    mock_post.return_value = _fake_response(200, {"status": "processando_autorizacao"})
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch)
    order = _order_with_item(restaurant, branch, product, manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)

    # "Processando" nao e falha — nao deve cair em contingencia.
    assert invoice.status == Invoice.STATUS_PENDING
    assert invoice.emission_type == Invoice.EMISSION_NORMAL


@patch("requests.post")
def test_rejected_response_falls_back_to_contingency(mock_post, account, restaurant, branch, manager_user):
    mock_post.return_value = _fake_response(200, {
        "status": "erro_autorizacao",
        "mensagem_sefaz": "Rejeicao: CNPJ do emitente invalido",
    })
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch)
    order = _order_with_item(restaurant, branch, product, manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)

    assert invoice.emission_type == Invoice.EMISSION_CONTINGENCY
    assert invoice.status == Invoice.STATUS_PENDING
    assert "CNPJ do emitente invalido" in invoice.error_message


@patch("requests.post")
def test_network_error_falls_back_to_contingency(mock_post, account, restaurant, branch, manager_user):
    import requests

    mock_post.side_effect = requests.ConnectionError("timeout")
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch)
    order = _order_with_item(restaurant, branch, product, manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)

    assert invoice.emission_type == Invoice.EMISSION_CONTINGENCY
    assert invoice.status == Invoice.STATUS_PENDING
