"""Duas notas da mesma série nunca saem com o mesmo número.

`config.next_number` sozinho era um voto de confiança. Qualquer coisa que
mexesse no contador sem olhar as notas já gravadas fazia a emissão seguinte
repetir um número: restauração de backup, edição pelo admin, sincronização do
cadastro com o provedor, ou uma base de demonstração semeada com números
altos — que foi o caso real, e produziu 68, 69 e 71 duplicados na série 1.

E repetir passava em silêncio: não há restrição de unicidade no banco, e quem
recusaria é a SEFAZ, na transmissão, com a venda fechada e o cliente esperando
o cupom.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.invoices.providers import FiscalProvider, register_provider
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.services import _proximo_numero_livre
from apps.orders.models import Order
from apps.orders.services import create_order


pytestmark = pytest.mark.django_db


@pytest.fixture
def contexto(account):
    with tenant_context(account):
        yield account


@pytest.fixture
def pedidos(contexto, restaurant, branch, manager_user):
    """Um pedido por nota: `Invoice.order` é um-para-um."""

    def criar(quantos):
        return [
            create_order(
                restaurant=restaurant, branch=branch,
                order_type=Order.TYPE_COUNTER, user=manager_user,
            )
            for _ in range(quantos)
        ]

    return criar


@pytest.fixture
def produto_faturavel(contexto, account, restaurant, branch):
    import uuid

    from apps.menu.models import Product

    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("25.00"),
    )


@pytest.fixture
def config(contexto, account, restaurant, branch):
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        document_model=FiscalConfig.MODEL_NFCE, series=1, next_number=70,
        environment="2", cnpj="63201558000155", uf="RJ",
    )


def _nota(config, account, restaurant, branch, order, *, numero, ambiente="2"):
    return Invoice.objects.create(
        account=account, restaurant=restaurant, branch=branch, order=order,
        series=config.series, number=numero,
        document_model=config.document_model, environment=ambiente,
    )


def test_sem_nota_gravada_o_contador_manda(config):
    assert _proximo_numero_livre(config) == 70


def test_numero_JA_GRAVADO_e_pulado(config, account, restaurant, branch, pedidos):
    """O caso real: a base tinha a 70 e o contador apontava para ela."""
    _nota(config, account, restaurant, branch, pedidos(1)[0], numero="70")

    assert _proximo_numero_livre(config) == 71


def test_pula_a_SEQUENCIA_inteira_de_numeros_ocupados(
    config, account, restaurant, branch, pedidos
):
    """Semeadura com um bloco de números: o salto é de uma vez só."""
    tres = pedidos(3)
    for indice, numero in enumerate(["70", "71", "72"]):
        _nota(config, account, restaurant, branch, tres[indice], numero=numero)

    assert _proximo_numero_livre(config) == 73


def test_HOMOLOGACAO_e_PRODUCAO_numeram_separado(config, account, restaurant, branch, pedidos):
    """A nota 70 de teste não gasta a 70 de verdade.

    São documentos de ambientes diferentes; a numeração de cada um corre
    sozinha, e misturá-las abriria buraco na série de produção por causa de
    um teste.
    """
    _nota(config, account, restaurant, branch, pedidos(1)[0], numero="70", ambiente="1")

    assert _proximo_numero_livre(config) == 70


def test_nota_SEM_numero_nao_ocupa_nada(config, account, restaurant, branch, pedidos):
    """Rascunho não tem número; contá-lo faria o contador fugir sozinho."""
    _nota(config, account, restaurant, branch, pedidos(1)[0], numero="")

    assert _proximo_numero_livre(config) == 70


def test_nota_de_OUTRA_SERIE_nao_ocupa_o_numero(config, account, restaurant, branch, pedidos):
    """A série é o que separa duas numerações no mesmo emitente."""
    nota = _nota(config, account, restaurant, branch, pedidos(1)[0], numero="70")
    Invoice.objects.filter(pk=nota.pk).update(series=2)

    assert _proximo_numero_livre(config) == 70


@register_provider
class _ProvedorQueAutoriza(FiscalProvider):
    """Autoriza na hora, como a SEFAZ no ar."""

    name = "test_numeracao"
    transmits = True

    def emit(self, invoice, config):
        invoice.provider = self.name
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000001"
        return invoice

    def cancel(self, invoice, reason):
        invoice.status = Invoice.STATUS_CANCELLED
        return invoice

    def status(self, invoice):
        return invoice.status


def test_a_EMISSAO_pega_o_numero_livre_e_nao_o_do_contador(
    config, account, restaurant, branch, pedidos, produto_faturavel
):
    """O teste que fecha o buraco: a função existir não basta.

    Os testes acima provam `_proximo_numero_livre`. Este prova que a EMISSÃO a
    usa — sem ele, trocar a chamada de volta por `config.next_number` passaria
    despercebido, que é exatamente o defeito original.
    """
    from apps.invoices.services import emit_fiscal_invoice
    from apps.orders.services import add_order_item

    ocupado, novo = pedidos(2)
    _nota(config, account, restaurant, branch, ocupado, numero="70")
    config.provider = _ProvedorQueAutoriza.name
    config.save(update_fields=["provider", "updated_at"])
    add_order_item(order=novo, product=produto_faturavel, quantity=1, user=novo.created_by)
    novo.refresh_from_db()

    nota = emit_fiscal_invoice(novo, user=novo.created_by)

    assert nota.number == "71", (
        "a emissao repetiu o numero 70, que ja estava gravado nesta serie"
    )
    config.refresh_from_db()
    assert config.next_number == 72


def test_o_contador_MANDADO_a_focus_tambem_pula_o_ocupado(
    config, account, restaurant, branch, pedidos
):
    """Quem numera a nota, com a Focus, é a FOCUS.

    O payload de emissão não leva `numero`: ela usa o contador do cadastro da
    empresa, e `apply_response` grava de volta o que ela devolveu. Mandar
    `next_number` cru repetia o defeito um nível acima — a Focus emitia sobre
    um número que a loja já sabia ocupado, e a SEFAZ devolvia "Duplicidade de
    NF-e, com diferença na Chave de Acesso".

    Aconteceu de verdade: a nota 71 foi reenviada e voltou rejeitada por causa
    da 68, que a Focus escolheu sozinha.
    """
    from apps.invoices.focus import build_focus_company_payload

    _nota(config, account, restaurant, branch, pedidos(1)[0], numero="70")

    payload = build_focus_company_payload(config, include_certificate=False)

    assert payload["proximo_numero_nfce_homologacao"] == "71", (
        "mandamos à Focus um número que já está gravado nesta série"
    )
