"""Fluxo fiscal completo pela API de verdade (não chamando os services
Python diretamente) — cobre exatamente o que o frontend/Flutter chamam:
emitir, reimprimir o DANFE e cancelar, além do CRUD de config/perfil.

Existe pra pegar bugs que só aparecem na camada HTTP (rota, barra final,
serializer, permissão) — foi assim que se achou o bug real de
`POST /invoices/emit` sem barra final virando redirect 301 e quebrando o
POST no navegador/Flutter (corrigido em PdvView.vue e home_page.dart).
"""
import uuid
from decimal import Decimal

import pytest

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, register_provider
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


@register_provider
class _ApiFlowProvider(FiscalProvider):
    name = "test_api_flow"

    def emit(self, invoice, config):
        invoice.provider = self.name
        invoice.status = Invoice.STATUS_PENDING
        return invoice

    def cancel(self, invoice, reason):
        invoice.status = Invoice.STATUS_CANCELLED
        invoice.error_message = reason or ""
        return invoice

    def status(self, invoice):
        return invoice.status


@register_provider
class _ApiResendFailsProvider(FiscalProvider):
    name = "test_api_resend_fails"

    def emit(self, invoice, config):
        raise RuntimeError("Rejeicao fiscal no reenvio")


@pytest.fixture
def account_with_financeiro(account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    return account


@pytest.fixture
def product(account, restaurant, branch):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"),
    )


@pytest.fixture
def order_with_item(restaurant, branch, product, manager_user):
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)
    return order


def test_emit_without_fiscal_config_returns_200_without_invoice(api_client, account_with_financeiro, order_with_item):
    resp = api_client.post("/api/v1/invoices/emit/", {"order": str(order_with_item.id)}, format="json")
    assert resp.status_code == 200
    assert resp.data["emitted"] is False
    assert "nao emitida" in resp.data["message"]
    assert not Invoice.all_objects.filter(order=order_with_item).exists()


def test_emit_unknown_order_returns_404(api_client, account_with_financeiro):
    resp = api_client.post("/api/v1/invoices/emit/", {"order": str(uuid.uuid4())}, format="json")
    assert resp.status_code == 404


def test_manual_provider_returns_200_without_creating_invoice(
    api_client, account_with_financeiro, account, restaurant, branch, order_with_item
):
    FiscalConfig.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        provider=FiscalConfig.PROVIDER_MANUAL,
        cnpj="11222333000181",
        uf="SP",
    )

    resp = api_client.post("/api/v1/invoices/emit/", {"order": str(order_with_item.id)}, format="json")

    assert resp.status_code == 200
    assert resp.data["emitted"] is False
    assert "Manual" in resp.data["message"]
    assert not Invoice.all_objects.filter(order=order_with_item).exists()


def test_focus_without_account_credentials_returns_200_without_creating_invoice(
    api_client, account_with_financeiro, account, restaurant, branch, order_with_item
):
    FiscalConfig.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        provider=FiscalConfig.PROVIDER_FOCUS_NFE,
        cnpj="11222333000181",
        uf="SP",
        focus_token_homologation="",
    )

    resp = api_client.post("/api/v1/invoices/emit/", {"order": str(order_with_item.id)}, format="json")

    assert resp.status_code == 200
    assert resp.data["emitted"] is False
    assert "nao emitida" in resp.data["message"]
    assert not Invoice.all_objects.filter(order=order_with_item).exists()


def test_fiscal_config_create_hides_secrets_on_read(api_client, account_with_financeiro, restaurant, branch):
    resp = api_client.post(
        "/api/v1/fiscal/config/",
        {
            "restaurant": str(restaurant.id), "branch": str(branch.id),
            "corporate_name": "Restaurante Teste LTDA", "cnpj": "11222333000181", "uf": "SP",
            "environment": FiscalConfig.ENV_HOMOLOGATION, "series": 1,
            "provider": FiscalConfig.PROVIDER_FOCUS_NFE,
            "provider_token": "segredo-super-secreto",
            "csc_token": "csc-secreto",
            "focus_certificate_base64": "certificado-base64",
            "focus_certificate_password": "senha-certificado",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert "provider_token" not in resp.data
    assert "csc_token" not in resp.data
    assert "focus_token_production" not in resp.data
    assert "focus_token_homologation" not in resp.data
    assert "focus_certificate_base64" not in resp.data
    assert "focus_certificate_password" not in resp.data
    assert resp.data["provider_token_configured"] is True
    assert resp.data["csc_token_configured"] is True
    assert resp.data["focus_certificate_configured"] is True
    assert resp.data["focus_certificate_password_configured"] is True

    listed = api_client.get("/api/v1/fiscal/config/")
    assert listed.status_code == 200
    assert all(
        "provider_token" not in row
        and "csc_token" not in row
        and "focus_token_production" not in row
        and "focus_token_homologation" not in row
        and "focus_certificate_base64" not in row
        and "focus_certificate_password" not in row
        for row in listed.data["results"]
    )


def test_fiscal_profile_crud_via_api(api_client, account_with_financeiro):
    """O perfil e um cadastro da conta: nasce sem restaurante/filial."""
    create_resp = api_client.post(
        "/api/v1/fiscal/profiles/",
        {"name": "Prato padrão", "cfop": "5102"},
        format="json",
    )
    assert create_resp.status_code == 201, create_resp.data
    profile_id = create_resp.data["id"]
    # Compartilhado entre restaurantes — como as categorias do cardapio.
    assert create_resp.data["restaurant"] is None
    assert create_resp.data["branch"] is None

    update_resp = api_client.patch(f"/api/v1/fiscal/profiles/{profile_id}/", {"is_default": True}, format="json")
    assert update_resp.status_code == 200
    assert update_resp.data["is_default"] is True

    list_resp = api_client.get("/api/v1/fiscal/profiles/")
    assert list_resp.status_code == 200
    assert any(row["id"] == profile_id for row in list_resp.data["results"])


def test_fiscal_profile_name_is_unique_per_account(api_client, account_with_financeiro):
    payload = {"name": "Bebida", "cfop": "5102"}
    assert api_client.post("/api/v1/fiscal/profiles/", payload, format="json").status_code == 201

    # 409 é o conflito padronizado da API para violação de unicidade.
    duplicated = api_client.post("/api/v1/fiscal/profiles/", payload, format="json")
    assert duplicated.status_code == 409, duplicated.data


def test_shared_fiscal_profile_is_visible_to_restaurant_scoped_user(
    api_client, admin_client, account_with_financeiro, restaurant
):
    """Um perfil da conta (restaurant=NULL) nao pode sumir para quem tem restaurante.

    O recorte por restaurante do `TenantQuerySetMixin` filtrava so pelo id e
    derrubava os compartilhados — o perfil reutilizavel ficava invisivel
    justamente para o operador, e some do dropdown filtrado por unidade.
    """
    created = admin_client.post("/api/v1/fiscal/profiles/", {"name": "Bebida"}, format="json")
    assert created.status_code == 201, created.data
    profile_id = created.data["id"]

    # `api_client` é o gerente, com restaurante/filial no perfil.
    listed = api_client.get("/api/v1/fiscal/profiles/")
    assert listed.status_code == 200
    assert any(row["id"] == profile_id for row in listed.data["results"])

    # E continua aparecendo quando a tela filtra por unidade (dropdown do produto).
    scoped = api_client.get("/api/v1/fiscal/profiles/", {"restaurant": str(restaurant.id)})
    assert scoped.status_code == 200
    assert any(row["id"] == profile_id for row in scoped.data["results"])


def test_product_reuses_one_fiscal_profile(api_client, account_with_financeiro, restaurant, branch):
    """1:N — um perfil serve varios produtos, de qualquer restaurante."""
    from apps.menu.models import Product

    profile_resp = api_client.post(
        "/api/v1/fiscal/profiles/", {"name": "Bebida", "cfop": "5102", "ncm": "22021000"}, format="json"
    )
    assert profile_resp.status_code == 201, profile_resp.data
    profile_id = profile_resp.data["id"]

    for index, name in enumerate(("Refrigerante", "Suco"), start=1):
        created = api_client.post(
            "/api/v1/menu/products/",
            {
                "restaurant": str(restaurant.id),
                "branch": str(branch.id),
                "name": name,
                "internal_code": f"BEB-{index}",
                "sale_price": "10.00",
                "fiscal_profile": profile_id,
            },
            format="json",
        )
        assert created.status_code == 201, created.data

    assert Product.all_objects.filter(fiscal_profile_id=profile_id).count() == 2


class TestFullEmissionFlow:
    """emitir -> filtrar por pedido -> imprimir -> cancelar, tudo via API."""

    @pytest.fixture(autouse=True)
    def setup(self, api_client, account, restaurant, branch, account_with_financeiro, order_with_item):
        FiscalConfig.objects.create(
            account=account, restaurant=restaurant, branch=branch,
            provider=_ApiFlowProvider.name, cnpj="11222333000181", uf="SP",
            environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        )
        self.client = api_client
        self.order = order_with_item

    def test_emit_returns_created_invoice(self):
        resp = self.client.post(
            "/api/v1/invoices/emit/",
            {"order": str(self.order.id), "cpf": "123.456.789-09", "cpf_name": "Cliente Teste"},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["emitted"] is True
        assert resp.data["access_key"]
        assert resp.data["access_key_formatted"]
        assert resp.data["status"] == Invoice.STATUS_PENDING
        assert resp.data["emission_type"] == Invoice.EMISSION_NORMAL
        assert resp.data["recipient_cpf"] == "12345678909"

    def test_emit_twice_for_same_order_returns_the_same_invoice(self):
        # Emitir e idempotente por pedido: com a emissao automatica do
        # pagamento, o PDV chega aqui com a nota do pedido ja criada, e
        # recusar a segunda chamada mostrava um erro numa venda que deu certo.
        first = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")
        assert first.status_code == 201
        second = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")
        assert second.status_code == 200
        assert second.data["id"] == first.data["id"]
        assert second.data["emitted"] is True

    def test_filter_invoices_by_order(self):
        emitted = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")
        invoice_id = emitted.data["id"]

        resp = self.client.get(f"/api/v1/invoices/?order={self.order.id}")
        assert resp.status_code == 200
        assert [row["id"] for row in resp.data["results"]] == [invoice_id]

    def test_print_danfe_is_refused_before_authorization(self):
        """DANFE de nota nao autorizada nao sai: a chave dela nao existe na SEFAZ."""
        emitted = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")

        resp = self.client.post(f"/api/v1/invoices/{emitted.data['id']}/print/", {}, format="json")

        assert resp.status_code == 400, resp.data
        assert emitted.data["printable"] is False
        assert emitted.data["fiscal_state"] == "awaiting_transmission"

    def test_print_danfe_after_emit(self):
        emitted = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")
        invoice_id = emitted.data["id"]
        invoice = Invoice.all_objects.get(pk=invoice_id)
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000001"
        invoice.save(update_fields=["status", "authorization_protocol", "updated_at"])

        resp = self.client.post(f"/api/v1/invoices/{invoice_id}/print/", {}, format="json")
        assert resp.status_code == 201, resp.data
        assert resp.data["print_job_id"]
        assert "DANFE" in resp.data["html"]

    def test_cancel_after_emit(self):
        emitted = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")
        invoice_id = emitted.data["id"]

        resp = self.client.post(f"/api/v1/invoices/{invoice_id}/cancel/", {"reason": "Pedido cancelado"}, format="json")
        assert resp.status_code == 200, resp.data
        assert resp.data["status"] == Invoice.STATUS_CANCELLED

    def test_resend_selected_contingency_invoice(self):
        emitted = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")
        invoice = Invoice.all_objects.get(pk=emitted.data["id"])
        invoice.emission_type = Invoice.EMISSION_CONTINGENCY
        invoice.error_message = "Falha temporaria"
        invoice.save(update_fields=["emission_type", "error_message", "updated_at"])

        response = self.client.post(f"/api/v1/invoices/{invoice.pk}/resend/", {}, format="json")

        assert response.status_code == 200, response.data
        assert response.data["id"] == str(invoice.pk)
        assert response.data["resent"] is True

    def test_resend_rejects_cancelled_invoice(self):
        emitted = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")
        invoice_id = emitted.data["id"]
        self.client.post(f"/api/v1/invoices/{invoice_id}/cancel/", {"reason": "Cancelada"}, format="json")

        response = self.client.post(f"/api/v1/invoices/{invoice_id}/resend/", {}, format="json")

        assert response.status_code == 400
        assert "autorizada ou cancelada" in str(response.data)

    def test_resend_returns_structured_error_and_keeps_invoice_details(self):
        emitted = self.client.post("/api/v1/invoices/emit/", {"order": str(self.order.id)}, format="json")
        invoice = Invoice.all_objects.get(pk=emitted.data["id"])
        invoice.emission_type = Invoice.EMISSION_CONTINGENCY
        invoice.save(update_fields=["emission_type", "updated_at"])
        config = FiscalConfig.all_objects.get(restaurant=self.order.restaurant)
        config.provider = _ApiResendFailsProvider.name
        config.save(update_fields=["provider", "updated_at"])

        response = self.client.post(f"/api/v1/invoices/{invoice.pk}/resend/", {}, format="json")

        assert response.status_code == 400, response.data
        assert response.data["resent"] is False
        assert response.data["error"] == {
            "code": "fiscal_resend_rejected",
            "message": "Rejeicao fiscal no reenvio",
        }
        assert response.data["invoice"]["id"] == str(invoice.pk)
        invoice.refresh_from_db()
        assert invoice.status == Invoice.STATUS_ERROR
