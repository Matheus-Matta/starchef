"""Terminal simulado: Caixa Principal, Caixa Secundario e aplicativo do garcom.

A cadeia de entrega e a mesma do sistema real:

    garcom/secundario --fila--> Caixa Principal --fila--> BACKEND

O secundario e o aplicativo nunca falam com a nuvem. Quando o principal esta
fora, a operacao fica na fila DELES; quando a nuvem esta fora, ela fica na fila
do principal. Os dois casos sao testados.
"""
import json
import time
import uuid

from .. import result as verdicts
from .outbox import DONE, FAILED, Outbox

PRINCIPAL = "principal"
SECONDARY = "secundario"
WAITER = "garcom"


class PrincipalDown(RuntimeError):
    """O Caixa Principal nao respondeu — quem chamou devolve para a propria fila."""


class Terminal:
    def __init__(self, ctx, suite, session, name, role=PRINCIPAL, upstream=None, time_scale=0.02):
        self.ctx = ctx
        self.suite = suite
        self.session = session
        self.name = name
        self.role = role
        self.upstream = upstream
        self.online = True
        self.outbox = Outbox(time_scale=time_scale)
        self.receipts = {}
        self.installation_id = session.terminal_id
        self.sales = []
        self.cash_register = None

    # -- estado ------------------------------------------------------------
    def go_offline(self, motivo=""):
        self.online = False
        self.ctx.note(self.suite, f"{self.name} ficou offline {motivo}".strip())

    def go_online(self):
        self.online = True

    # -- entrega -----------------------------------------------------------
    def execute(self, operation, force_queue=False):
        """Aplica a operacao. Online entrega agora; offline enfileira e segue.

        `force_queue` existe porque uma venda que COMECOU na fila tem de
        continuar nela: mandar o item por HTTP citando um `offline-<uuid>` que
        o servidor nunca viu so produz 404 — e nao e o que o PDV faz.
        """
        if force_queue or not self.online:
            self.outbox.enqueue(operation)
            return None
        try:
            status, corpo = self.deliver(operation)
        except PrincipalDown:
            self.outbox.enqueue(operation)
            return None
        if 200 <= status < 300:
            operation.status = DONE
            if operation.local_id and isinstance(corpo, dict) and corpo.get("id"):
                self.outbox.resolve_id(operation.local_id, str(corpo["id"]))
            return corpo
        if status in (0, 408, 425, 429, 500, 502, 503, 504):
            # Falha temporaria nao perde a venda: volta para a fila.
            self.outbox.enqueue(operation)
            return None
        operation.status = FAILED
        operation.last_error = f"HTTP {status}"
        return None

    def deliver(self, operation):
        """Entrega de verdade: pelo relay (secundario/garcom) ou pela API."""
        if self.upstream is not None:
            return self.upstream.relay(operation, origem=self.name)
        return self.call_api(operation)

    def call_api(self, operation):
        inicio = time.time()
        resposta = self.session.client.request(
            operation.method,
            operation.path,
            body=operation.body or None,
            headers=self.session.headers(idempotency_key=operation.operation_id),
        )
        self.ctx.record(
            self.suite, f"{self.role}:{operation.kind}", operation.method, operation.path, resposta,
            expectation=operation.expectation, case=operation.case,
            payload=json.dumps(operation.body, ensure_ascii=False, default=str)[:400], started=inicio,
        )
        return resposta.status, (resposta.json() or {})

    def relay(self, operation, origem=""):
        """Recebe a operacao de um terminal cliente (papel do Caixa Principal)."""
        if not self.online:
            raise PrincipalDown(f"{self.name} indisponivel para {origem}")
        recibo = self.receipts.get(operation.operation_id)
        if recibo is not None:
            # Recibo por operation_id: repetir nao cria segunda venda (§Caixa Secundario).
            self.outbox.replayed_duplicates += 1
            return recibo
        status, corpo = self.call_api(operation)
        if 200 <= status < 300:
            self.receipts[operation.operation_id] = (status, corpo)
        return status, corpo

    # -- reconciliacao -----------------------------------------------------
    def reconnect(self):
        """Volta a rede e escoa a fila, exatamente como o SyncService faz."""
        self.go_online()
        return self.outbox.drain(self.deliver)

    def replay_duplicate(self, operation):
        """Reenvia a MESMA operacao — o teste de idempotencia de ponta a ponta."""
        inicio = time.time()
        resposta = self.session.client.request(
            operation.method, operation.path, body=operation.body or None,
            headers=self.session.headers(idempotency_key=operation.operation_id),
        )
        self.ctx.record(
            self.suite, f"{self.role}:reenvio_idempotente", operation.method, operation.path, resposta,
            expectation=verdicts.ANY, case="mesma_chave_de_idempotencia", started=inicio,
        )
        return resposta

    def local_id(self):
        return f"offline-{uuid.uuid4()}"

    def summary(self):
        return {
            "terminal": self.name,
            "papel": self.role,
            "vendas": len(self.sales),
            "fila_pendente": len(self.outbox.pending),
            "fila_recusada": len(self.outbox.blocked),
            "entregues": self.outbox.delivered,
            "recibos_repetidos": self.outbox.replayed_duplicates,
        }
