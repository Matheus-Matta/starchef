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
from rest_framework.test import APIClient

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FocusNfeProvider
from apps.invoices.services import emit_fiscal_invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.payments.models import Payment, PaymentMethod

pytestmark = pytest.mark.django_db


def _make_product(account, restaurant, branch):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
    )


def _make_fiscal_config(account, restaurant, branch):
    account_config = account.focus_nfe_config
    account_config.homologation_url = "https://homologacao.focusnfe.com.br"
    account_config.production_url = "https://api.focusnfe.com.br"
    account_config.save(update_fields=["homologation_url", "production_url", "updated_at"])
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=FocusNfeProvider.name, focus_token_homologation="fake-token",
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
    assert sent_payload["data_emissao"]
    assert sent_payload["indicador_inscricao_estadual_destinatario"] == "9"
    assert sent_payload["local_destino"] == "1"
    assert sent_payload["consumidor_final"] == "1"
    assert sent_payload["finalidade_emissao"] == "1"
    assert sent_payload["presenca_comprador"] == "1"
    assert sent_payload["formas_pagamento"] == [{"forma_pagamento": "90", "valor_pagamento": "0.00"}]
    assert len(sent_payload["items"]) == 1
    assert sent_payload["items"][0]["descricao"] == "X-Burger"


@patch("requests.post")
def test_payload_maps_approved_payments_and_cash_change(mock_post, account, restaurant, branch, manager_user):
    mock_post.return_value = _fake_response(200, {
        "status": "autorizado",
        "chave_nfe": "35" + "0" * 42,
        "protocolo": "135250000000001",
    })
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch)
    order = _order_with_item(restaurant, branch, product, manager_user)
    cash = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Dinheiro", method_type="cash"
    )
    pix = PaymentMethod.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="PIX", method_type="pix"
    )
    Payment.objects.create(
        account=account, restaurant=restaurant, branch=branch, order=order,
        payment_method=cash, amount=Decimal("20.00"), change_amount=Decimal("5.00"),
    )
    Payment.objects.create(
        account=account, restaurant=restaurant, branch=branch, order=order,
        payment_method=pix, amount=Decimal("5.00"),
    )

    emit_fiscal_invoice(order, user=manager_user)

    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["formas_pagamento"] == [
        {"forma_pagamento": "01", "valor_pagamento": "25.00"},
        {"forma_pagamento": "17", "valor_pagamento": "5.00"},
    ]
    assert sent_payload["valor_troco"] == "5.00"


@patch("requests.post")
def test_payload_maps_order_fees_to_other_expenses(mock_post, account, restaurant, branch, manager_user):
    mock_post.return_value = _fake_response(200, {
        "status": "autorizado",
        "chave_nfe": "35" + "0" * 42,
        "protocolo": "135250000000001",
    })
    product = _make_product(account, restaurant, branch)
    _make_fiscal_config(account, restaurant, branch)
    order = _order_with_item(restaurant, branch, product, manager_user)
    order.service_fee = Decimal("2.50")
    order.delivery_fee = Decimal("1.50")
    order.discount = Decimal("1.00")
    order.total = Decimal("28.00")
    order.save(update_fields=["service_fee", "delivery_fee", "discount", "total", "updated_at"])

    emit_fiscal_invoice(order, user=manager_user)

    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["valor_produtos"] == "25.00"
    assert sent_payload["valor_desconto"] == "1.00"
    assert sent_payload["valor_outras_despesas"] == "4.00"
    assert sent_payload["valor_total"] == "28.00"
    assert sent_payload["items"][0]["valor_desconto"] == "1.00"
    assert sent_payload["items"][0]["valor_outras_despesas"] == "4.00"


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


@patch("requests.post")
def test_nfe_model_uses_nfe_endpoint_and_synced_environment_token(
    mock_post, account, restaurant, branch, manager_user
):
    mock_post.return_value = _fake_response(202, {"status": "processando_autorizacao"})
    product = _make_product(account, restaurant, branch)
    config = _make_fiscal_config(account, restaurant, branch)
    config.document_model = FiscalConfig.MODEL_NFE
    config.provider_token = ""
    config.focus_token_homologation = "empresa-homologacao"
    config.save(update_fields=["document_model", "provider_token", "focus_token_homologation", "updated_at"])
    order = _order_with_item(restaurant, branch, product, manager_user)

    invoice = emit_fiscal_invoice(order, user=manager_user)

    assert invoice.provider_reference == f"starchef-{invoice.id}"
    assert "/v2/nfe?ref=starchef-" in mock_post.call_args.args[0]
    assert mock_post.call_args.kwargs["auth"] == ("empresa-homologacao", "")


@patch("requests.post")
def test_focus_webhook_updates_async_invoice(mock_post, account, restaurant, branch, manager_user):
    account_config = account.focus_nfe_config
    account_config.webhook_authorization = "webhook-secret"
    account_config.webhook_authorization_header = "X-Focus-Auth"
    account_config.save(update_fields=["webhook_authorization", "webhook_authorization_header", "updated_at"])
    mock_post.return_value = _fake_response(202, {"status": "processando_autorizacao"})
    product = _make_product(account, restaurant, branch)
    config = _make_fiscal_config(account, restaurant, branch)
    config.document_model = FiscalConfig.MODEL_NFE
    config.save(update_fields=["document_model", "updated_at"])
    order = _order_with_item(restaurant, branch, product, manager_user)
    invoice = emit_fiscal_invoice(order, user=manager_user)

    response = APIClient().post(
        "/api/v1/integrations/focus-nfe/webhook/",
        {
            "ref": invoice.provider_reference,
            "status": "autorizado",
            "chave_nfe": "35" + "1" * 42,
            "protocolo": "135250000000002",
            "numero": "99",
            "serie": "2",
        },
        format="json",
        HTTP_X_FOCUS_AUTH="webhook-secret",
    )

    assert response.status_code == 200, response.data
    invoice.refresh_from_db()
    assert invoice.status == Invoice.STATUS_ISSUED
    assert invoice.number == "99"
    assert invoice.series == 2
    assert invoice.authorization_protocol == "135250000000002"
