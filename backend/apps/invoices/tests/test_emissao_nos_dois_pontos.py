"""Loja E nuvem emitindo pela ACBrLib, cada uma com a sua série.

Com o interruptor `cloud_emission` desligado (o padrão), nada muda: a nuvem
deixa a nota da conta com servidor de loja para a loja. Ligado, a venda FEITA
NA NUVEM (pedido na faixa da nuvem) é emitida lá, na `cloud_series`; a venda
feita na loja continua sendo da loja, na `series`.

Série separada, e não "trocar o último número pela sincronização": com a loja
sem internet os dois lados não se enxergam, e qualquer contador compartilhado
entregaria o mesmo número dos dois lados. Série diferente não colide nunca.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction

from apps.invoices.emissao_da_loja import (
    emitir_pagos_sem_nota,
    motivo_para_a_nuvem_nao_emitir,
    serie_desta_emissao,
)
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.serializers import FiscalConfigSerializer
from apps.invoices.tests.quitacao import quitar_pedido
from apps.orders.sequence_ranges import PRIMEIRO_NUMERO_DA_NUVEM
from apps.synchronization.constants import NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db

VENDA_DA_NUVEM = PRIMEIRO_NUMERO_DA_NUVEM + 3
VENDA_DA_LOJA = 42


@pytest.fixture
def nuvem_com_loja(settings, account, restaurant):
    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "cloud"
    SyncNode.objects.create(pair_id=uuid.uuid4(), account=account, restaurant=restaurant,
                            node_type=NodeType.LOCAL, name="Loja", status="ACTIVE")


def _config(**extra):
    base = {"provider": FiscalConfig.PROVIDER_ACBRLIB, "series": 1, "cloud_emission": False,
            "cloud_series": None}
    return SimpleNamespace(**{**base, **extra})


def _pedido(account, restaurant, sequence):
    return SimpleNamespace(account_id=account.id, restaurant_id=restaurant.id, sequence=sequence)


def test_desligado_a_nuvem_continua_deixando_tudo_para_a_loja(nuvem_com_loja, account, restaurant):
    config = _config()
    assert motivo_para_a_nuvem_nao_emitir(_pedido(account, restaurant, VENDA_DA_NUVEM), config)


def test_ligado_a_nuvem_emite_a_venda_feita_nela_na_serie_dela(nuvem_com_loja, account, restaurant):
    config = _config(cloud_emission=True, cloud_series=2)
    pedido = _pedido(account, restaurant, VENDA_DA_NUVEM)
    assert motivo_para_a_nuvem_nao_emitir(pedido, config) == ""
    assert serie_desta_emissao(pedido, config) == (2, "cloud_next_number")


def test_ligado_a_venda_feita_na_loja_continua_sendo_da_loja(nuvem_com_loja, account, restaurant):
    """A nuvem emitindo uma venda da loja = duas notas para o mesmo pedido, uma
    de cada lado, porque a loja também a emite ao receber o pagamento."""
    config = _config(cloud_emission=True, cloud_series=2)
    assert motivo_para_a_nuvem_nao_emitir(_pedido(account, restaurant, VENDA_DA_LOJA), config)


def test_na_loja_a_serie_e_sempre_a_da_loja(settings, account, restaurant):
    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "local"
    config = _config(cloud_emission=True, cloud_series=2)
    assert serie_desta_emissao(_pedido(account, restaurant, VENDA_DA_NUVEM), config) == (1, "next_number")


def test_conta_so_nuvem_usa_a_serie_normal(settings, account, restaurant):
    """Sem loja a nuvem é o único emissor: não há com quem dividir a série."""
    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "cloud"
    config = _config(cloud_emission=True, cloud_series=2)
    assert serie_desta_emissao(_pedido(account, restaurant, VENDA_DA_NUVEM), config) == (1, "next_number")


def test_a_loja_nao_varre_a_venda_que_a_nuvem_emite(settings, monkeypatch, account, restaurant,
                                                    branch, manager_user):
    """Ligado, a venda feita na nuvem é emitida LÁ. Se a loja também a varresse,
    ao chegar paga e ainda sem nota (a nota vem atrás), o pedido teria duas."""
    from apps.orders.models import Order
    from apps.orders.services import create_order

    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "local"
    FiscalConfig.objects.create(account=account, restaurant=restaurant, branch=branch, series=1,
                                provider=FiscalConfig.PROVIDER_ACBRLIB, cnpj="11222333000181",
                                cloud_emission=True, cloud_series=2)
    da_loja = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                           user=manager_user)
    da_nuvem = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                            user=manager_user)
    Order.all_objects.filter(pk=da_nuvem.pk).update(sequence=VENDA_DA_NUVEM)
    Order.all_objects.filter(pk__in=[da_loja.pk, da_nuvem.pk]).update(status=Order.STATUS_PAID)
    # Aqui o assunto é QUAL pedido a loja varre; o pedido inteiro (itens e
    # pagamentos) é conferido em test_nota_de_pedido_incompleto.py.
    monkeypatch.setattr("apps.invoices.pedido_completo.motivo_do_pedido_incompleto", lambda _p: None)
    emitidos = []
    monkeypatch.setattr("apps.invoices.services.issue_invoice_for_paid_order",
                        lambda pedido, **_k: emitidos.append(pedido.pk) or object())

    assert emitir_pagos_sem_nota() == 1
    assert emitidos == [da_loja.pk]


def test_a_nuvem_numera_na_serie_dela_e_anda_o_contador_dela(nuvem_com_loja, monkeypatch, account,
                                                             restaurant, branch, manager_user):
    from apps.invoices.services import emit_fiscal_invoice
    from apps.invoices.tests.test_acbrlib_provider import EMITENTE
    from apps.menu.models import Product
    from apps.orders.models import Order
    from apps.orders.services import add_order_item, create_order

    config = FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, uf="SP", cnpj="11222333000181",
        provider=FiscalConfig.PROVIDER_ACBRLIB, series=1, next_number=50,
        cloud_emission=True, cloud_series=2, cloud_next_number=7, **EMITENTE,
    )
    monkeypatch.setattr("apps.invoices.services.get_provider", lambda _p: SimpleNamespace(
        transmits=True, emit=lambda nota, _c: setattr(nota, "status", Invoice.STATUS_ISSUED)))
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                          user=manager_user)
    assert pedido.sequence >= PRIMEIRO_NUMERO_DA_NUVEM
    produto = Product.objects.create(account=account, restaurant=restaurant, branch=branch,
                                     name="Suco", internal_code=f"S{uuid.uuid4().hex[:6]}",
                                     sale_price=Decimal("12.50"))
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    quitar_pedido(pedido)
    nota = emit_fiscal_invoice(pedido, user=manager_user)

    assert (nota.series, nota.number) == (2, "7")
    assert nota.access_key[22:25] == "002"
    config.refresh_from_db()
    assert (config.next_number, config.cloud_next_number) == (50, 8)


def test_serie_da_nuvem_obrigatoria_e_diferente_da_loja(account, restaurant, branch):
    base = {"provider": FiscalConfig.PROVIDER_ACBRLIB, "series": 1, "cloud_emission": True}
    for extra in ({}, {"cloud_series": 1}):
        dados = FiscalConfigSerializer(data={**base, **extra}, partial=True)
        assert not dados.is_valid()
        assert "cloud_series" in dados.errors
    assert FiscalConfigSerializer(data={**base, "cloud_series": 2}, partial=True).is_valid()


def test_o_banco_recusa_a_mesma_serie_nos_dois_pontos(account, restaurant, branch):
    """O `if` do serializer não protege o admin nem o shell: a trava é do banco."""
    with pytest.raises(IntegrityError), transaction.atomic():
        FiscalConfig.objects.create(account=account, restaurant=restaurant, branch=branch,
                                    series=1, cloud_emission=True, cloud_series=1)


def test_o_modo_viaja_e_o_contador_da_nuvem_nao():
    entrada = registry.require("fiscal_config")
    payload = serialization.serialize(FiscalConfig(), entrada)
    assert {"cloud_emission", "cloud_series"} <= set(payload)
    assert "cloud_next_number" in entrada.local_only_fields
