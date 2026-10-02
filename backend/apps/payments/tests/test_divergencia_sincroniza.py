"""A divergência sobe e desce inteira — e a análise não vira conflito.

Campo novo não tem trava automática na sincronização: foi assim que
`ScaleReading.notes` nunca chegou à nuvem. Aqui se confere o payload.
"""
from decimal import Decimal

import pytest

import apps.synchronization.catalog  # noqa: F401 — registra o catálogo
from apps.payments.discrepancy import SalesDiscrepancy
from apps.synchronization.constants import ConflictResolution
from apps.synchronization.services import serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


def test_payload_leva_valor_formas_status_e_desfecho(sessao_de_caixa, admin_user):
    sessao = sessao_de_caixa()
    linha = SalesDiscrepancy.all_objects.create(
        account=sessao.account, restaurant=sessao.restaurant, branch=sessao.branch,
        cash_register=sessao, amount=Decimal("12.34"), reason="Sem registro no PDV",
        by_payment_method=[{"payment_method": "x", "name": "PIX", "method_type": "pix", "amount": "12.34"}],
        status=SalesDiscrepancy.STATUS_REGULARIZED, regularization_note="Protocolo 1",
        created_by=admin_user, updated_by=admin_user,
    )

    campos = serialization.serialize(linha, registry.get("sales_discrepancy"))

    for nome in ("cash_register_id", "amount", "by_payment_method", "reason", "status",
                 "regularization_note", "regularized_at", "cancel_reason"):
        assert any(chave.startswith(nome.removesuffix("_id")) for chave in campos), (nome, sorted(campos))


def test_versao_mais_nova_vence_porque_o_status_so_anda_para_frente():
    entrada = registry.get("sales_discrepancy")

    assert entrada.conflict_policy == ConflictResolution.LAST_VERSION
    assert entrada.flow == "both"
