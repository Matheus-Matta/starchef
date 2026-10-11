"""Dois caixas emitindo no mesmo segundo não pegam o mesmo número.

Achado no teste de 200 emissões pela ACBrLib no par Docker, com 4 caixas em
paralelo: 45 números repetidos na série 1. Cada emissão trava o SEU pedido,
mas lia `FiscalConfig.next_number` sem trava — o segundo caixa lia o contador
antes de o primeiro gravar e saía com o mesmo número. A SEFAZ recusaria a
segunda com "Duplicidade de NF-e, com diferença na Chave de Acesso".

O teste reproduz a corrida sem threads: a emissão recebe a configuração lida
ANTES de outro caixa avançar o contador — é exatamente o que o segundo caixa
via. A correção trava a linha da configuração e relê o contador depois da trava.
"""
import pytest

from apps.invoices.models import FiscalConfig
from apps.invoices.services import emit_fiscal_invoice
from apps.invoices.tests.test_numeracao_nao_repete import (  # noqa: F401 — fixtures
    _ProvedorQueAutoriza, config, contexto, pedidos, produto_faturavel,
)
from apps.orders.services import add_order_item

pytestmark = pytest.mark.django_db


def test_emissao_rele_o_contador_depois_da_trava_e_nao_repete_numero(
    config, pedidos, produto_faturavel, monkeypatch  # noqa: F811 — fixtures importadas
):
    config.provider = _ProvedorQueAutoriza.name
    config.save(update_fields=["provider", "updated_at"])
    lida_antes = FiscalConfig.objects.get(pk=config.pk)  # next_number = 70
    # O outro caixa emitiu e avançou o contador nesse meio-tempo.
    FiscalConfig.objects.filter(pk=config.pk).update(next_number=71)
    monkeypatch.setattr("apps.invoices.services._resolve_fiscal_config", lambda *a, **k: lida_antes)

    pedido = pedidos(1)[0]
    add_order_item(order=pedido, product=produto_faturavel, quantity=1, user=pedido.created_by)
    nota = emit_fiscal_invoice(pedido, user=pedido.created_by)

    assert nota.number == "71", "a emissão usou o contador lido antes da trava e repetiu o 70"
    config.refresh_from_db()
    assert config.next_number == 72
