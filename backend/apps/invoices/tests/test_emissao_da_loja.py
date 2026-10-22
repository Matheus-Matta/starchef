"""Com ACBrLib, a nota da venda de uma loja é emitida pela LOJA.

Dois emissores na mesma série (loja e nuvem, cada um com o seu contador)
repetiriam número. A nuvem deixa a nota para a loja; a loja emite sozinha a
venda paga que chegou sem nota; e o contador não viaja na sincronização.
"""
import uuid
from types import SimpleNamespace

import pytest

from apps.invoices.emissao_da_loja import emitir_pagos_sem_nota, motivo_para_a_nuvem_nao_emitir
from apps.invoices.models import FiscalConfig
from apps.synchronization.constants import NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


def _config(provider):
    return SimpleNamespace(provider=provider)


def test_na_nuvem_a_venda_de_loja_com_servidor_fica_para_a_loja(settings, account, restaurant):
    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "cloud"
    pedido = SimpleNamespace(account_id=account.id, restaurant_id=restaurant.id)
    assert motivo_para_a_nuvem_nao_emitir(pedido, _config(FiscalConfig.PROVIDER_ACBRLIB)) == ""

    SyncNode.objects.create(pair_id=uuid.uuid4(), account=account, restaurant=restaurant,
                            node_type=NodeType.LOCAL, name="Loja", status="ACTIVE")

    assert motivo_para_a_nuvem_nao_emitir(pedido, _config(FiscalConfig.PROVIDER_ACBRLIB))
    # A Focus segue como sempre: o contador dela é um só, o da própria Focus.
    assert motivo_para_a_nuvem_nao_emitir(pedido, _config(FiscalConfig.PROVIDER_FOCUS_NFE)) == ""


def test_na_loja_a_venda_paga_sem_nota_e_emitida(settings, monkeypatch, account, restaurant, branch,
                                                 manager_user):
    from apps.orders.models import Order
    from apps.orders.services import create_order

    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "local"
    FiscalConfig.objects.create(account=account, restaurant=restaurant, branch=branch,
                                provider=FiscalConfig.PROVIDER_ACBRLIB, cnpj="11222333000181")
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    Order.all_objects.filter(pk=pedido.pk).update(status=Order.STATUS_PAID)
    # Aqui o assunto é QUAL pedido a loja varre; o pedido inteiro (itens e
    # pagamentos) é conferido em test_nota_de_pedido_incompleto.py.
    monkeypatch.setattr("apps.invoices.pedido_completo.motivo_do_pedido_incompleto", lambda _p: None)
    emitidos = []
    monkeypatch.setattr("apps.invoices.services.issue_invoice_for_paid_order",
                        lambda pedido, **_k: emitidos.append(pedido.pk) or object())

    assert emitir_pagos_sem_nota() == 1
    assert emitidos == [pedido.pk]


def test_fora_da_loja_ninguem_varre(settings):
    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "cloud"
    assert emitir_pagos_sem_nota() == 0


def test_o_contador_da_numeracao_nao_viaja():
    """Com "vence o mais novo", uma edição do cadastro na nuvem trazia o contador
    velho de volta e a próxima nota da loja repetia número."""
    assert "next_number" in registry.require("fiscal_config").local_only_fields
