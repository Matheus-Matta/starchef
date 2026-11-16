"""Falhas de propósito nos caminhos que a loja usa o dia inteiro.

Cada teste quebra uma coisa de um jeito que acontece de verdade — dado
corrompido vindo da sincronização, PDV mandando lixo, rede repetindo o mesmo
"Concluir", o processo morrendo com a SEFAZ já tendo autorizado, Redis fora —
e confere três coisas:

1. **nunca 500**: erro de dado é 4xx com motivo; erro de infraestrutura é
   absorvido onde a venda já foi gravada;
2. **nada pela metade**: venda recusada não deixa pedido, item nem pagamento;
3. **recuperação sozinha**: o que ficou pendente volta ao normal sem ninguém
   rodar comando.
"""
import uuid
from datetime import timedelta

import pytest
from django.db import OperationalError
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, register_provider
from apps.kitchen.models import KdsColumn, KdsStation
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, create_order, send_order_to_kitchen
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db

URL_VENDA = "/api/v1/orders/submit/"


def _cliente(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


@pytest.fixture
def loja(restaurant):
    restaurant.require_open_cash_register = False
    restaurant.save(update_fields=["require_open_cash_register"])
    return restaurant


def _venda(loja_, produto_, forma_, **trocas):
    corpo = {
        "id": str(uuid.uuid4()), "order_type": "counter", "restaurant": str(loja_.pk),
        "items": [{"id": str(uuid.uuid4()), "product": str(produto_.pk), "quantity": 1}],
        "payments": [{"id": str(uuid.uuid4()), "payment_method": str(forma_.pk),
                      "amount": str(produto_.sale_price), "client_updated_at": "2026-11-15T12:00:00Z"}],
    }
    corpo.update(trocas)
    return corpo


# ── 1. KDS com regra corrompida ────────────────────────────────────────────


@pytest.mark.parametrize("regras", [
    pytest.param(["lixo", 42, None], id="elementos-que-nao-sao-regra"),
    pytest.param([{"action": "include", "priority": "alta"}, {"action": "include", "priority": 1}],
                 id="prioridade-texto-misturada-com-numero"),
    pytest.param([{"action": "move", "target_column": str(uuid.uuid4()), "conditions": []}],
                 id="coluna-alvo-que-nao-existe"),
    pytest.param([{"action": "include", "conditions": "minutes_since_sent>5"}],
                 id="condicoes-em-texto"),
    pytest.param([{"action": "exclude", "conditions": [None, "x", {"field": None}]}],
                 id="condicoes-com-lixo"),
    pytest.param({"action": "include"}, id="regras-num-objeto-e-nao-lista"),
])
def test_kds_com_regra_corrompida_ainda_mostra_o_quadro(
    regras, account, restaurant, branch, table, product, manager_user
):
    """A regra vem de JSON livre e chega também pela sincronização e pelo
    admin, sem passar pelo serializer. Uma regra quebrada não pode apagar a
    cozinha inteira com um 500 a cada 15 s."""
    estacao = KdsStation.objects.create(account=account, restaurant=restaurant, name="Cozinha",
                                        rules=regras)
    KdsColumn.objects.create(account=account, station=estacao, name="A fazer", position=0, is_entry=True)
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE,
                          table=table, user=manager_user)
    add_order_item(order=pedido, product=product, quantity=1, user=manager_user)
    send_order_to_kitchen(pedido, manager_user)

    resposta = _cliente(manager_user).get("/api/v1/kitchen/items/", {"station": str(estacao.pk)})

    assert resposta.status_code == 200, resposta.content[:300]


# ── 2. Venda malformada ou hostil ──────────────────────────────────────────

def _corpos_hostis(restaurant, product, payment_method):
    base = lambda **t: _venda(restaurant, product, payment_method, **t)  # noqa: E731
    item = lambda **t: [{"id": str(uuid.uuid4()), "product": str(product.pk), "quantity": 1, **t}]  # noqa: E731
    pagamento = lambda **t: [{"id": str(uuid.uuid4()), "payment_method": str(payment_method.pk),  # noqa: E731
                              "amount": "10.00", "client_updated_at": "2026-11-15T12:00:00Z", **t}]
    repetido = str(uuid.uuid4())
    return {
        "itens-em-texto": base(items="abc"),
        "itens-num-objeto": base(items={"product": str(product.pk)}),
        "quantidade-negativa": base(items=item(quantity=-1)),
        "quantidade-zero": base(items=item(quantity=0)),
        "quantidade-NaN": base(items=item(quantity="NaN")),
        "quantidade-infinita": base(items=item(quantity="1e309")),
        "quantidade-gigante": base(items=item(quantity=10 ** 30)),
        "produto-nao-e-uuid": base(items=[{"id": str(uuid.uuid4()), "product": "'; DROP TABLE x;--",
                                           "quantity": 1}]),
        "produto-que-nao-existe": base(items=[{"id": str(uuid.uuid4()), "product": str(uuid.uuid4()),
                                               "quantity": 1}]),
        "item-sem-produto": base(items=[{"id": str(uuid.uuid4()), "quantity": 1}]),
        "dois-itens-com-o-mesmo-id": base(items=[
            {"id": repetido, "product": str(product.pk), "quantity": 1},
            {"id": repetido, "product": str(product.pk), "quantity": 2},
        ]),
        "pagamento-negativo": base(payments=pagamento(amount="-25.00")),
        "pagamento-em-texto": base(payments=pagamento(amount="vinte reais")),
        "forma-de-pagamento-inexistente": base(payments=pagamento(payment_method=str(uuid.uuid4()))),
        "pagamentos-em-texto": base(payments="dinheiro"),
        "id-da-venda-invalido": base(id="nao-e-uuid"),
        "tipo-de-pedido-invalido": base(order_type="drone"),
        "restaurante-que-nao-existe": base(restaurant=str(uuid.uuid4())),
        "observacao-de-200-mil-caracteres": base(items=item(customer_note="x" * 200_000)),
        "corpo-lista": [base()],
        "corpo-vazio": {},
    }


NOMES_HOSTIS = [
    "itens-em-texto", "itens-num-objeto", "quantidade-negativa", "quantidade-zero",
    "quantidade-NaN", "quantidade-infinita", "quantidade-gigante", "produto-nao-e-uuid",
    "produto-que-nao-existe", "item-sem-produto", "dois-itens-com-o-mesmo-id",
    "pagamento-negativo", "pagamento-em-texto", "forma-de-pagamento-inexistente",
    "pagamentos-em-texto", "id-da-venda-invalido", "tipo-de-pedido-invalido",
    "restaurante-que-nao-existe", "observacao-de-200-mil-caracteres", "corpo-lista", "corpo-vazio",
]


@pytest.mark.parametrize("nome", NOMES_HOSTIS)
def test_venda_hostil_vira_4xx_e_nao_deixa_nada_pela_metade(
    nome, loja, product, payment_method, manager_user
):
    corpo = _corpos_hostis(loja, product, payment_method)[nome]
    pedidos_antes = Order.all_objects.count()
    itens_antes = OrderItem.all_objects.count()
    pagamentos_antes = Payment.all_objects.count()

    resposta = _cliente(manager_user).post(URL_VENDA, corpo, format="json")

    assert resposta.status_code < 500, f"{nome}: {resposta.status_code} {resposta.content[:300]}"
    if resposta.status_code >= 400:
        assert Order.all_objects.count() == pedidos_antes, f"{nome}: pedido gravado numa venda recusada"
        assert OrderItem.all_objects.count() == itens_antes, f"{nome}: item gravado numa venda recusada"
        assert Payment.all_objects.count() == pagamentos_antes, f"{nome}: pagamento gravado"
        corpo_erro = resposta.json()
        assert corpo_erro.get("error", {}).get("message"), f"{nome}: recusa sem motivo"


def test_o_mesmo_concluir_reenviado_tres_vezes_e_uma_venda_so(loja, product, payment_method, manager_user):
    """O PDV desiste aos 20 s e manda de novo; a rede pode entregar as duas."""
    corpo = _venda(loja, product, payment_method)
    cliente = _cliente(manager_user)

    respostas = [cliente.post(URL_VENDA, corpo, format="json") for _ in range(3)]

    assert all(r.status_code in (200, 201) for r in respostas), [r.status_code for r in respostas]
    assert Order.all_objects.filter(pk=corpo["id"]).count() == 1
    assert Payment.all_objects.filter(order_id=corpo["id"], status=Payment.STATUS_APPROVED).count() == 1
    assert OrderItem.all_objects.filter(order_id=corpo["id"]).count() == 1


# ── 3. Fiscal: o processo morre com a SEFAZ já tendo autorizado ───────────

class _Sefaz:
    autorizadas = set()
    explode_com = None


@register_provider
class _SefazQueAutoriza(FiscalProvider):
    name = "test_falhas_sefaz"
    transmits = True

    def emit(self, invoice, config):
        if _Sefaz.explode_com:
            raise _Sefaz.explode_com
        _Sefaz.autorizadas.add(invoice.access_key)
        invoice.provider = self.name
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000077"
        return invoice

    def cancel(self, invoice, reason):
        invoice.status = Invoice.STATUS_CANCELLED
        return invoice

    def status(self, invoice):
        if invoice.access_key in _Sefaz.autorizadas:
            invoice.provider = self.name
            invoice.status = Invoice.STATUS_ISSUED
            invoice.authorization_protocol = "135260000000077"
        return invoice.status


@pytest.fixture
def emissao(account, restaurant, branch, product, manager_user):
    _Sefaz.autorizadas = set()
    _Sefaz.explode_com = None
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, provider=_SefazQueAutoriza.name,
        document_model=FiscalConfig.MODEL_NFCE, series=1, next_number=1,
        environment="2", cnpj="63201558000155", uf="RJ",
    )

    def novo_pedido():
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER,
                              user=manager_user)
        add_order_item(order=pedido, product=product, quantity=1, user=manager_user)
        return pedido

    return novo_pedido


def test_processo_morre_depois_da_sefaz_autorizar_e_a_nota_se_recupera(emissao, manager_user, monkeypatch):
    from apps.invoices import services
    from apps.invoices.services import EM_VOO, emit_fiscal_invoice, reprocess_pending_fiscal_invoices

    pedido = emissao()

    def banco_cai(_invoice):
        raise OperationalError("server closed the connection unexpectedly")

    monkeypatch.setattr(services, "_preservar_marcas_do_voo", banco_cai)
    with pytest.raises(OperationalError):
        emit_fiscal_invoice(pedido, user=manager_user)
    monkeypatch.undo()

    nota = Invoice.all_objects.get(order=pedido)
    # A SEFAZ autorizou, mas o banco não ficou sabendo: a nota está "em voo".
    assert nota.status == Invoice.STATUS_PENDING
    assert EM_VOO in nota.fiscal_payload
    assert nota.access_key in _Sefaz.autorizadas

    # A próxima venda não reusa o número da nota que ficou no meio do caminho.
    outra = emit_fiscal_invoice(emissao(), user=manager_user)
    assert int(outra.number) == int(nota.number) + 1

    # Dentro do prazo, ninguém mexe nela (o processo podia estar vivo).
    reprocess_pending_fiscal_invoices()
    nota.refresh_from_db()
    assert nota.status == Invoice.STATUS_PENDING

    # Passado o prazo, a varredura consulta e a nota se resolve sozinha.
    payload = {**nota.fiscal_payload, EM_VOO: (timezone.now() - timedelta(minutes=10)).isoformat()}
    Invoice.all_objects.filter(pk=nota.pk).update(fiscal_payload=payload)
    reprocess_pending_fiscal_invoices()
    nota.refresh_from_db()
    assert nota.status == Invoice.STATUS_ISSUED
    assert EM_VOO not in nota.fiscal_payload
    assert "awaiting" not in nota.fiscal_payload


@pytest.mark.parametrize("erro", [
    pytest.param(RuntimeError("bug no comunicador"), id="excecao-inesperada"),
    pytest.param(KeyError("cStat"), id="resposta-sem-campo"),
    pytest.param(ValueError("XML invalido"), id="xml-quebrado"),
])
def test_provedor_quebrado_nao_deixa_nota_presa_em_voo(erro, emissao, manager_user):
    from apps.invoices.services import EM_VOO, emit_fiscal_invoice

    _Sefaz.explode_com = erro
    nota = emit_fiscal_invoice(emissao(), user=manager_user)

    nota.refresh_from_db()
    assert nota.status == Invoice.STATUS_ERROR
    assert EM_VOO not in (nota.fiscal_payload or {})
    assert nota.error_message


# ── 4. Infraestrutura fora do ar ───────────────────────────────────────────

def test_tarefa_do_celery_que_falha_nao_vaza_o_lote_de_avisos(monkeypatch):
    from celery import shared_task

    from apps.realtime import envio_em_lote
    from apps.realtime.events import broadcast_model_event

    enviados = []

    class Camada:
        async def group_send(self, grupo, mensagem):
            enviados.append(mensagem["payload"]["id"])

    monkeypatch.setattr(envio_em_lote, "get_channel_layer", Camada)

    @shared_task(name="tests.falhas.quebra_no_meio")
    def quebra_no_meio():
        broadcast_model_event("c1", "model.updated", {"resource": "orders.order", "id": "gravado"})
        raise RuntimeError("quebrou depois de gravar")

    with pytest.raises(RuntimeError):
        quebra_no_meio.apply()  # em modo eager a exceção sobe (CELERY_TASK_EAGER_PROPAGATES)

    # O que foi gravado antes de quebrar é avisado (a escrita existe)...
    assert enviados == ["gravado"]
    # ...e o lote não fica aberto: o próximo aviso, fora de tarefa, sai na hora.
    broadcast_model_event("c1", "model.updated", {"resource": "orders.order", "id": "depois"})
    assert enviados == ["gravado", "depois"]


def test_cache_fora_do_ar_nao_derruba_a_fila_de_impressao(loja, manager_user, monkeypatch):
    from django.core.cache import cache

    from apps.orders import services

    chamadas = []
    monkeypatch.setattr(services, "dispatch_due_kitchen_batches",
                        lambda **kw: chamadas.append(kw) or 0)

    def redis_fora(*_a, **_k):
        raise ConnectionError("Error 111 connecting to redis:6379")

    monkeypatch.setattr(cache, "add", redis_fora)
    resposta = _cliente(manager_user).get("/api/v1/print-jobs/", {"restaurant": str(loja.pk)})

    assert resposta.status_code == 200, resposta.content[:300]
    assert chamadas, "sem cache, a rede de segurança da leitura deixou de liberar as rodadas"


def test_redis_fora_na_venda_nao_vira_500(loja, product, payment_method, manager_user, monkeypatch):
    """Broker e canal de tempo real caídos: a venda já foi gravada."""
    from apps.realtime import envio_em_lote

    class CamadaQuebrada:
        async def group_send(self, *_a):
            raise ConnectionError("redis fora")

    monkeypatch.setattr(envio_em_lote, "get_channel_layer", CamadaQuebrada)
    monkeypatch.setattr("apps.invoices.tasks.emitir_nota_do_pedido_pago_task.delay",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("broker fora")))

    corpo = _venda(loja, product, payment_method)
    resposta = _cliente(manager_user).post(URL_VENDA, corpo, format="json")

    assert resposta.status_code == 201, resposta.content[:300]
    assert Order.all_objects.get(pk=corpo["id"]).status == Order.STATUS_PAID
