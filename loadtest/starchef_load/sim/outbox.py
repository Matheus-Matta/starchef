"""A fila de saida do terminal — o Transactional Outbox do PDV, em Python.

Espelha o comportamento documentado em `docs/PDV_OFFLINE_SCALE_ARCHITECTURE.md`:
FIFO por ordem de criacao, `operation_id` = chave de idempotencia, barreira por
dependencia (fechamento espera os itens), escada de retentativa para falha
temporaria e `FAILED` definitivo para recusa de regra de negocio.

A escada roda com o relogio comprimido (`time_scale`): 5s viram 0,1s. O que
importa aqui e a ORDEM e o efeito, nao esperar cinco minutos de verdade.
"""
import itertools
import json
import time
import uuid

PENDING = "PENDING"
FAILED = "FAILED"
DONE = "DONE"

BACKOFF = (5, 15, 30, 60, 300)
TEMPORARY_STATUS = (0, 408, 425, 429, 500, 502, 503, 504)
MAX_PER_CYCLE = 20

_counter = itertools.count(1)


class Operation:
    """Uma mutacao esperando entrega."""

    __slots__ = ("seq", "operation_id", "method", "path", "body", "kind", "local_id",
                 "status", "attempts", "next_retry_at", "last_error", "barrier", "expectation", "case")

    def __init__(self, method, path, body=None, *, kind="", local_id="", barrier=False,
                 expectation="accept", case="valido"):
        self.seq = next(_counter)
        self.operation_id = str(uuid.uuid4())
        self.method = method
        self.path = path
        self.body = body or {}
        self.kind = kind or method
        self.local_id = local_id
        self.status = PENDING
        self.attempts = 0
        self.next_retry_at = 0.0
        self.last_error = ""
        self.barrier = barrier
        self.expectation = expectation
        self.case = case

    def references_unresolved(self):
        """Cita um ID local que ainda nao virou definitivo?"""
        alvo = self.path + json.dumps(self.body, default=str)
        return "offline-" in alvo and not self.local_id

    def __repr__(self):
        return f"<Op {self.seq} {self.method} {self.path} {self.status}>"


class Outbox:
    """Fila de um terminal. Uma instancia por PDV/aparelho simulado."""

    def __init__(self, time_scale=0.02):
        self.operations = []
        self.id_map = {}
        self.time_scale = time_scale
        self.delivered = 0
        self.failed = 0
        self.replayed_duplicates = 0

    def enqueue(self, operation):
        self.operations.append(operation)
        return operation

    @property
    def pending(self):
        return [op for op in self.operations if op.status == PENDING]

    @property
    def blocked(self):
        return [op for op in self.operations if op.status == FAILED]

    def resolve_id(self, local_id, server_id):
        """Troca o ID temporario pelo definitivo na fila inteira (registerResolvedId)."""
        if not local_id or not server_id:
            return
        self.id_map[local_id] = server_id
        for operation in self.operations:
            if operation.status != PENDING:
                continue
            if local_id in operation.path:
                operation.path = operation.path.replace(local_id, server_id)
            corpo = json.dumps(operation.body, default=str)
            if local_id in corpo:
                operation.body = json.loads(corpo.replace(local_id, server_id))

    def _eligible(self, now):
        """FIFO, mas quem esta em espera cede a vez para quem e independente."""
        prontas = []
        for operation in sorted(self.pending, key=lambda op: op.seq):
            if operation.next_retry_at > now:
                continue
            if operation.references_unresolved():
                continue
            prontas.append(operation)
            if operation.barrier:
                break
            if len(prontas) >= MAX_PER_CYCLE:
                break
        return prontas

    def drain(self, deliver, cycles=0):
        """Entrega a fila ate ela parar de progredir.

        O criterio de parada e PROGRESSO, nao numero de voltas. Uma barreira
        (fechamento, recebimento, envio a cozinha) encerra o lote do ciclo assim
        que entra nele, entao um ciclo pode entregar UMA operacao — e um teto
        fixo de voltas deixava centenas para tras num apagao grande, que o
        relatorio mostrava como "operacoes presas". Era limite do teste, nao do
        PDV.

        `deliver(op) -> (status, corpo)`; qualquer excecao conta como status 0
        (falha de transporte), que e retentavel.
        """
        teto = cycles if cycles > 0 else 20000
        paradas = 0
        for _ in range(teto):
            if not self.pending:
                break
            antes = self.delivered + self.failed
            prontas = self._eligible(time.time())
            if not prontas:
                paradas += 1
                if paradas > 3:
                    break  # so resta operacao em espera longa ou orfa de dependencia
                time.sleep(min(0.1, self.time_scale * 5))
                continue
            for operation in prontas:
                self._deliver_one(operation, deliver)
            # Nenhuma das prontas saiu do lugar: insistir so gastaria tempo.
            paradas = 0 if (self.delivered + self.failed) > antes else paradas + 1
            if paradas > 3:
                break
        return self.status()

    def status(self):
        """Quem sobrou e por que — sem isto, "11 pendentes" nao aciona ninguem."""
        agora = time.time()
        pendentes = self.pending
        return {
            "entregues": self.delivered,
            "recusadas": self.failed,
            "pendentes": len(pendentes),
            "em_espera": sum(1 for op in pendentes if op.next_retry_at > agora),
            "orfas": sum(1 for op in pendentes if op.references_unresolved()),
            "ultimo_erro": next((op.last_error for op in reversed(pendentes) if op.last_error), ""),
        }

    def _deliver_one(self, operation, deliver):
        operation.attempts += 1
        try:
            status, corpo = deliver(operation)
        except Exception as exc:  # noqa: BLE001 — falha de transporte e resultado, nao acidente
            status, corpo = 0, {"detail": str(exc)}
        if 200 <= status < 300:
            operation.status = DONE
            self.delivered += 1
            if operation.local_id and isinstance(corpo, dict) and corpo.get("id"):
                self.resolve_id(operation.local_id, str(corpo["id"]))
            return
        if status in TEMPORARY_STATUS:
            espera = BACKOFF[min(operation.attempts - 1, len(BACKOFF) - 1)] * self.time_scale
            operation.next_retry_at = time.time() + espera
            operation.last_error = f"HTTP {status}"
            if operation.attempts > len(BACKOFF) + 1:
                operation.status = FAILED
                self.failed += 1
            return
        operation.status = FAILED
        operation.last_error = f"HTTP {status}: {str(corpo)[:160]}"
        self.failed += 1
        # Uma criacao recusada leva junto quem dependia dela (descarte em cadeia).
        if operation.local_id:
            for outra in self.pending:
                if operation.local_id in outra.path or operation.local_id in json.dumps(outra.body, default=str):
                    outra.status = FAILED
                    outra.last_error = f"dependia da operacao {operation.seq}"
                    self.failed += 1
