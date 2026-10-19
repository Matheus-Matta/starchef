"""Ajudantes dos testes da NFC-e na venda: ligar a nota e montar a venda.

Funções, e não fixtures: importar fixture de outro arquivo de teste esconde de
onde ela vem e o ruff (F811) acusa — com função, cada teste diz o que liga.
"""
import uuid

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.tests.test_auto_issue_on_payment import _AutoIssueProvider

URL_VENDA = "/api/v1/orders/submit/"
URL_NOTA = "/api/v1/invoices/emit/"


def ligar_nota(account, restaurant, branch, provider=_AutoIssueProvider.name):
    """Restaurante que emite NFC-e, com o módulo financeiro (rota da nota)."""
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, provider=provider,
        cnpj="11222333000181", uf="SP", environment=FiscalConfig.ENV_HOMOLOGATION,
        series=1, next_number=1,
    )


def venda(restaurant, produto, forma, *, valor="25.00", itens=1, comandas=(), **extra):
    """O corpo que o PDV manda no "Concluir": pedido, itens e recebimento."""
    return {
        "id": str(uuid.uuid4()), "order_type": "counter", "restaurant": str(restaurant.pk),
        "items": [{"id": str(uuid.uuid4()), "product": str(produto.pk), "quantity": 1}
                  for _ in range(itens)],
        "commands": [str(c.pk) for c in comandas],
        "payments": [{"id": str(uuid.uuid4()), "payment_method": str(forma.pk), "amount": valor,
                      "client_updated_at": "2026-10-18T12:00:00Z"}],
        **extra,
    }


def notas_do(pedido_id):
    return Invoice.all_objects.filter(order_id=pedido_id)
