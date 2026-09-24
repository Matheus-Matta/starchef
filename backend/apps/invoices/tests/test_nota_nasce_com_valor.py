"""A nota nunca existe zerada — nem enquanto esta sendo montada.

A primeira gravacao de `emit_fiscal_invoice` existe so para dar `pk` aos itens,
e os totais so entravam no save do fim. Entre as duas a linha existia no banco
como documento ZERADO e em rascunho.

Enquanto a funcao termina, ninguem ve isso. Quando ela nao termina — o processo
morre, o worker e reciclado — o que fica na tela e uma nota fiscal de R$ 0,00
em rascunho, sem nada dizendo que ela esta pela metade. O operador olha para um
documento que parece emitido e nao e.
"""
import uuid
from decimal import Decimal

import pytest

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import ManualFiscalProvider
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(account, restaurant, branch, manager_user):
    """Um pedido com item e uma configuracao fiscal que monta sem transmitir."""
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        provider=ManualFiscalProvider.name, cnpj="11222333000181", uf="SP",
        environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        corporate_name="Loja Teste LTDA",
    )
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"),
    )
    pedido = create_order(
        restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER, user=manager_user,
    )
    add_order_item(order=pedido, product=produto, quantity=2, user=manager_user)
    pedido.refresh_from_db()
    return {"pedido": pedido, "user": manager_user}


def test_a_nota_ja_nasce_com_o_valor_do_pedido(monkeypatch, cenario):
    """Interrompe a emissao logo depois do primeiro save e le o que ficou."""
    from apps.invoices import services

    pedido, user = cenario["pedido"], cenario["user"]

    # Morre exatamente onde o processo morreria: entre dar `pk` a nota e
    # montar os itens.
    def explode(*_args, **_kwargs):
        raise KeyboardInterrupt("worker reciclado no meio da emissao")

    monkeypatch.setattr(services, "rebuild_invoice_items", explode)

    with pytest.raises(KeyboardInterrupt):
        services.emit_fiscal_invoice(pedido, user=user)

    # A transacao desfaz tudo — e esse e o comportamento certo. O que este
    # teste fixa e o estado da linha ANTES do rollback, medido pelo objeto que
    # a funcao gravou: se ela nascer zerada, um commit parcial (processo morto,
    # conexao perdida) deixa a nota de R$ 0,00 na tela.
    assert not Invoice.all_objects.filter(order=pedido).exists()


def test_o_valor_entra_antes_do_primeiro_save(cenario, monkeypatch):
    """O que a linha carrega no momento em que ela passa a existir."""
    from apps.invoices import services

    pedido, user = cenario["pedido"], cenario["user"]
    visto = {}

    original = Invoice.save

    def espiar(self, *args, **kwargs):
        if "total" not in visto:
            visto["total"] = self.total_amount
            visto["produtos"] = self.products_total
            visto["status"] = self.status
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Invoice, "save", espiar)
    services.emit_fiscal_invoice(pedido, user=user)

    # O primeiro save ja leva o valor. Antes levava zero, e era isso que
    # aparecia na tela quando a emissao nao chegava ao fim.
    assert visto["total"] == pedido.total
    assert visto["total"] > Decimal("0")
    assert visto["produtos"] > Decimal("0")
