"""Lei 12.741/2012: o cupom do consumidor mostra os tributos aproximados.

A linha só saía quando o valor passava de zero. Com o percentual do perfil
fiscal em 0% — o padrão de quem não preencheu —, ela simplesmente sumia, e a
loja descumpria a lei sem nada avisar.
"""
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig, FiscalProfile, Invoice
from apps.invoices.services import _danfe_nfce_text, emit_fiscal_invoice, print_fiscal_invoice
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


def _nota(account, restaurant, branch, user, percentual):
    perfil = FiscalProfile.objects.create(
        account=account, name=f"Prato {uuid.uuid4().hex[:4]}", ncm="21069090", cfop="5102",
        csosn="102", approx_tax_rate=Decimal(percentual))
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Prato feito",
        internal_code=f"P{uuid.uuid4().hex[:6]}", sale_price=Decimal("25.00"), fiscal_profile=perfil)
    config = FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, provider="manual",
        cnpj="11222333000181", uf="SP", environment=FiscalConfig.ENV_HOMOLOGATION,
        series=1, next_number=1)
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user)
    add_order_item(order=pedido, product=produto, quantity=1, user=user)
    return emit_fiscal_invoice(pedido, user=user), config


def _texto(nota, config):
    with tenant_context(nota.account):
        return _danfe_nfce_text(nota, config)


def test_o_cupom_mostra_os_tributos_com_o_texto_da_lei(account, restaurant, branch, manager_user):
    nota, config = _nota(account, restaurant, branch, manager_user, "17.28")

    linhas = _texto(nota, config).splitlines()

    i = next(n for n, linha in enumerate(linhas) if linha.startswith("TRIBUTOS TOTAIS INCIDENTES"))
    assert linhas[i].endswith("4,32")
    assert linhas[i + 1] == "(LEI FEDERAL 12.741/2012)"


def test_com_percentual_zerado_a_linha_sai_mesmo_assim(account, restaurant, branch, manager_user):
    nota, config = _nota(account, restaurant, branch, manager_user, "0")

    texto = _texto(nota, config)

    assert "TRIBUTOS TOTAIS INCIDENTES R$" in texto and "(LEI FEDERAL 12.741/2012)" in texto


def test_o_cupom_em_html_tambem_mostra(account, restaurant, branch, manager_user):
    nota, _config = _nota(account, restaurant, branch, manager_user, "0")
    nota.status, nota.authorized_at = Invoice.STATUS_ISSUED, timezone.now()
    nota.save(update_fields=["status", "authorized_at"])

    html = print_fiscal_invoice(nota, user=manager_user).html_content

    assert "Tributos Totais Incidentes" in html and "Lei Federal 12.741/2012" in html


def test_percentual_zerado_fica_avisado_na_nota_sem_bloquear(account, restaurant, branch, manager_user):
    nota, _config = _nota(account, restaurant, branch, manager_user, "0")

    assert nota.status != Invoice.STATUS_ERROR
    assert "Prato feito" in nota.fiscal_payload["aviso_lei_12741"]


def test_percentual_preenchido_nao_avisa(account, restaurant, branch, manager_user):
    nota, _config = _nota(account, restaurant, branch, manager_user, "17.28")

    assert "aviso_lei_12741" not in nota.fiscal_payload
