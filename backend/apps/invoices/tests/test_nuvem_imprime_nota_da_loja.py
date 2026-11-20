"""A nuvem IMPRIME a nota que a loja emitiu pela ACBrLib.

Produção, 19/11/2026: na retaguarda web, "Emitir nota fiscal / DANFE" de uma
venda da loja respondia "Venda feita na loja: a nota é emitida pelo servidor da
loja" — mesmo com a nota já autorizada e sincronizada para a nuvem. A recusa
existe para a nuvem não EMITIR uma segunda nota; ela vinha antes de olhar a
nota que o pedido já tem, e o DANFE nunca saía da web.
"""
import uuid

import pytest

from apps.invoices.models import Invoice
from apps.invoices.services import emit_fiscal_invoice
from apps.invoices.tests.test_acbrlib_provider import Comunicador, ambiente  # noqa: F401
from apps.synchronization.constants import NodeType
from apps.synchronization.models import SyncNode

pytestmark = pytest.mark.django_db

EMITIR = "/api/v1/invoices/emit/"


def _virar_nuvem_com_loja(settings, ambiente):  # noqa: F811
    conta = ambiente.pedido.account
    conta.enabled_modules = ["financeiro"]
    conta.save(update_fields=["enabled_modules"])
    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "cloud"
    SyncNode.objects.create(pair_id=uuid.uuid4(), account=ambiente.pedido.account,
                            restaurant=ambiente.pedido.restaurant, node_type=NodeType.LOCAL,
                            name="Loja", status="ACTIVE")


def test_nota_da_loja_ja_na_nuvem_volta_imprimivel(ambiente, monkeypatch, settings, api_client):  # noqa: F811
    # A loja emite (é o que a sincronização traz para a nuvem).
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", Comunicador("online"))
    nota = emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)
    assert nota.status == Invoice.STATUS_ISSUED
    _virar_nuvem_com_loja(settings, ambiente)

    resposta = api_client.post(EMITIR, {"order": str(ambiente.pedido.id)}, format="json")

    assert resposta.status_code == 200, resposta.content
    assert resposta.data["id"] == str(nota.id)
    assert resposta.data["printable"] is True
    danfe = api_client.post(f"/api/v1/invoices/{nota.id}/print/", {}, format="json")
    assert danfe.status_code == 201, danfe.content
    assert nota.access_key and danfe.data["html"]
    assert Invoice.all_objects.filter(order=ambiente.pedido).count() == 1


def test_sem_a_nota_da_loja_a_nuvem_continua_sem_emitir(ambiente, settings, api_client):  # noqa: F811
    _virar_nuvem_com_loja(settings, ambiente)

    resposta = api_client.post(EMITIR, {"order": str(ambiente.pedido.id)}, format="json")

    assert resposta.status_code == 200
    assert resposta.data["emitted"] is False
    assert "loja" in resposta.data["message"]
    assert not Invoice.all_objects.filter(order=ambiente.pedido).exists()
