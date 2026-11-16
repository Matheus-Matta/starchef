"""Regressões dos 500 que a varredura da API (`bench_varredura_da_api.py`) achou.

Cada caso é a requisição exata que derrubava a rota. A regra é a mesma do
resto do projeto: corpo com tipo errado é 4xx com motivo, nunca 500.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.inbound_nfe.models import DFeSyncState, InboundNFe, InboundNFeItem
from apps.payments.services import open_cash_register

pytestmark = pytest.mark.django_db


# ── NSU manual da NF-e de entrada ─────────────────────────────────────────


def test_set_nsu_responde_200_com_o_nsu_gravado(admin_client, account):
    """Gravava e respondia 500 sempre (`return None` no fim da view)."""
    resposta = admin_client.post("/api/v1/inbound-nfe/set-nsu/", {"ult_nsu": "1234"}, format="json")

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["ult_nsu"] == "000000000001234"
    assert DFeSyncState.all_objects.filter(account=account, ult_nsu="000000000001234").exists()


@pytest.mark.parametrize("nsu", ["lixo", "", "12a", "1" * 16, -1, [], {"a": 1}, True, 1.5])
def test_set_nsu_recusa_o_que_nao_e_numero(admin_client, account, nsu):
    """`"lixo"` virava o NSU `0000000000lixo` e quebrava a próxima consulta."""
    resposta = admin_client.post("/api/v1/inbound-nfe/set-nsu/", {"ult_nsu": nsu}, format="json")

    assert resposta.status_code == 400, resposta.content
    assert not DFeSyncState.all_objects.filter(account=account).exists()


def test_set_nsu_aceita_zero(admin_client):
    """`0` é o NSU de recomeçar do início — o `or` antigo o tratava como ausente."""
    resposta = admin_client.post("/api/v1/inbound-nfe/set-nsu/", {"ult_nsu": 0}, format="json")

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["ult_nsu"] == "0" * 15


# ── Item da NF-e de entrada: só as ações, sem CRUD ────────────────────────


@pytest.fixture
def item_recebido(account, restaurant):
    nota = InboundNFe.objects.create(
        account=account, restaurant=restaurant,
        access_key="35260812345678000199550010000000011000000011",
        number="1", series="1", supplier_name="Fornecedor", supplier_cnpj="98765432000188",
        issue_date=timezone.now(), status=InboundNFe.STATUS_RECEIVED,
    )
    return InboundNFeItem.objects.create(
        account=account, invoice=nota, item_number=1, supplier_code="X", description="ITEM",
        commercial_quantity=Decimal("1"), commercial_unit="UN",
        commercial_unit_value=Decimal("10"), product_total=Decimal("10"),
    )


def test_item_de_nota_recebida_nao_pode_ser_apagado(admin_client, item_recebido):
    """O DELETE herdado do CRUD apagava o item sem `assert_item_editable`,
    separando a nota do estoque que ela já tinha lançado."""
    resposta = admin_client.delete(f"/api/v1/inbound-nfe-items/{item_recebido.pk}/")

    assert resposta.status_code in (404, 405), resposta.content
    assert InboundNFeItem.all_objects.filter(pk=item_recebido.pk).exists()


@pytest.mark.parametrize("metodo", ["post", "put", "patch"])
def test_item_de_nota_nao_tem_escrita_generica(admin_client, item_recebido, metodo):
    """POST/PUT/PATCH davam 500 (viewset sem `serializer_class`)."""
    alvo = "/api/v1/inbound-nfe-items/" if metodo == "post" else f"/api/v1/inbound-nfe-items/{item_recebido.pk}/"
    resposta = getattr(admin_client, metodo)(alvo, {"description": "x"}, format="json")

    assert resposta.status_code in (404, 405), resposta.content


def test_acao_do_item_continua_funcionando(admin_client, item_recebido):
    """O `map` (o que a tela usa) segue de pé — e respeita a trava de nota recebida."""
    resposta = admin_client.post(
        f"/api/v1/inbound-nfe-items/{item_recebido.pk}/map/", {"product_id": None}, format="json",
    )

    assert resposta.status_code in (400, 409), resposta.content


# ── Cupom com código que não é texto ──────────────────────────────────────


@pytest.mark.parametrize("codigo", [[], {"a": 1}, True])
def test_cupom_com_codigo_que_nao_e_texto_e_400(admin_client, codigo):
    resposta = admin_client.post("/api/v1/promotions/coupons/validate/", {"code": codigo}, format="json")

    assert resposta.status_code < 500, resposta.content


def test_cupom_numerico_e_procurado_como_texto(admin_client):
    """O PDV pode mandar `123` sem aspas: é o cupom "123", não lixo."""
    resposta = admin_client.post("/api/v1/promotions/coupons/validate/", {"code": 123}, format="json")

    assert resposta.status_code < 500, resposta.content
    assert "123" in resposta.content.decode()


# ── Pedido do garçom com tipo em lista ────────────────────────────────────


@pytest.mark.parametrize("tipo", [["counter"], {"a": 1}, 1])
def test_create_with_item_com_tipo_que_nao_e_texto_e_400(api_client, tipo):
    resposta = api_client.post("/api/v1/orders/create-with-item/", {"order_type": tipo}, format="json")

    assert resposta.status_code == 400, resposta.content


# ── Aprovação do caixa com justificativa nula ─────────────────────────────


@pytest.mark.parametrize("motivo", [None, [], {"a": 1}, 5])
def test_aprovar_caixa_sem_justificativa_texto_e_400(api_client, account, restaurant, branch, manager_user, motivo):
    with tenant_context(account):
        sessao = open_cash_register(
            restaurant=restaurant, branch=branch, user=manager_user, opening_amount=Decimal("10.00")
        )
    resposta = api_client.post(f"/api/v1/cash-register/{sessao.pk}/approve/", {"reason": motivo}, format="json")

    assert resposta.status_code == 400, resposta.content
    assert "justificativa" in resposta.content.decode().lower()


# ── Listagem de NF-e de entrada sem N+1 ───────────────────────────────────


def _notas(account, restaurant, quantas, inicio=0):
    for n in range(inicio, inicio + quantas):
        nota = InboundNFe.objects.create(
            account=account, restaurant=restaurant, access_key=f"{n:044d}", number=str(n), series="1",
            supplier_name="F", supplier_cnpj="98765432000188", issue_date=timezone.now(),
            status=InboundNFe.STATUS_PENDING_MAPPING,
        )
        for i, ignorado in enumerate((False, True, False)):
            InboundNFeItem.objects.create(
                account=account, invoice=nota, item_number=i + 1, supplier_code=str(i), description="I",
                commercial_quantity=Decimal("1"), commercial_unit="UN", is_ignored=ignorado,
                commercial_unit_value=Decimal("1"), product_total=Decimal("1"),
            )


def test_listagem_de_notas_nao_consulta_por_linha(admin_client, account, restaurant):
    """4 COUNT + 1 SELECT por nota: 50 notas eram ~250 consultas."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    _notas(account, restaurant, 2)
    with CaptureQueriesContext(connection) as poucas:
        resposta = admin_client.get("/api/v1/inbound-nfe/")
    assert resposta.status_code == 200, resposta.content
    _notas(account, restaurant, 8, inicio=2)
    with CaptureQueriesContext(connection) as muitas:
        resposta = admin_client.get("/api/v1/inbound-nfe/")

    assert len(muitas) == len(poucas), "a listagem consulta uma vez por nota"
    linha = resposta.json()["results"][0]
    assert (linha["items_count"], linha["ignored_items_count"], linha["active_items_count"]) == (3, 1, 2)
    assert (linha["unmapped_items_count"], linha["has_unmapped_items"]) == (2, True)
    assert linha["latest_manifestation"] is None


# ── 429 em português e sem ERROR no log ───────────────────────────────────


def test_limite_de_requisicoes_responde_em_portugues_e_loga_como_aviso(caplog):
    import logging

    from rest_framework.exceptions import NotFound, Throttled

    from apps.core.exceptions import api_exception_handler

    with caplog.at_level(logging.WARNING, logger="api.errors"):
        resposta = api_exception_handler(Throttled(wait=3599), {})
        api_exception_handler(NotFound(), {})

    assert resposta.status_code == 429
    assert "Muitas requisições. Tente de novo em 1 h." in str(resposta.data["error"]["message"])
    assert "Expected" not in str(resposta.data)
    assert [r.levelname for r in caplog.records if r.name == "api.errors"] == ["WARNING", "WARNING"]
