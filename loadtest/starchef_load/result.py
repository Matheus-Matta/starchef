"""O resultado de uma requisicao e o veredito que ela recebe.

O ponto do teste nao e "quantas responderam 200". E: *o servidor se comportou
como deveria diante do que foi mandado?* Por isso toda requisicao carrega uma
EXPECTATIVA, e o veredito compara resposta com expectativa.
"""
from dataclasses import dataclass, field

# Expectativas -------------------------------------------------------------
ACCEPT = "accept"  # payload valido: o servidor DEVE aceitar (2xx)
REJECT = "reject"  # payload sujo: o servidor DEVE recusar com 4xx claro
ANY = "any"  # comportamento aceitavel nos dois sentidos; so nao pode quebrar

# Vereditos ----------------------------------------------------------------
OK = "ok"
REJECTED_OK = "recusa_correta"
GARBAGE_ACCEPTED = "lixo_aceito"
VALID_REJECTED = "valido_recusado"
SERVER_ERROR = "erro_servidor"
TRANSPORT_ERROR = "falha_transporte"
THROTTLED = "limitado"
#: 503 com Retry-After: o servidor DISSE que esta sobrecarregado (pool de
#: banco esgotado, por exemplo). E capacidade, nao defeito de rota — conta a
#: parte, como o 429.
OVERLOADED = "sobrecarga"
CONFLICT = "conflito"

#: Vereditos que sao defeito do sistema, nao do teste.
DEFECTS = (SERVER_ERROR, TRANSPORT_ERROR, GARBAGE_ACCEPTED)
#: Vereditos que merecem olhar humano, mas podem ter causa legitima.
SUSPECTS = (VALID_REJECTED, CONFLICT)

VERDICT_LABELS = {
    OK: "aceitou o valido",
    REJECTED_OK: "recusou o invalido",
    GARBAGE_ACCEPTED: "ACEITOU DADO INVALIDO",
    VALID_REJECTED: "recusou um payload que deveria valer",
    SERVER_ERROR: "ERRO 5xx (quebrou)",
    TRANSPORT_ERROR: "NAO RESPONDEU (conexao/timeout)",
    THROTTLED: "throttle 429",
    OVERLOADED: "sobrecarga 503 (Retry-After)",
    CONFLICT: "conflito 409",
}


def classify(expectation, status, error):
    """Traduz (expectativa, status, erro de transporte) em um veredito."""
    if error:
        return TRANSPORT_ERROR
    if status == 503:
        return OVERLOADED
    if status >= 500:
        return SERVER_ERROR
    if status == 429:
        return THROTTLED
    if expectation == REJECT:
        return REJECTED_OK if 400 <= status < 500 else GARBAGE_ACCEPTED
    if expectation == ANY:
        return OK if status < 400 else REJECTED_OK
    if 200 <= status < 300:
        return OK
    if status == 409:
        return CONFLICT
    return VALID_REJECTED


@dataclass
class RequestResult:
    """Uma requisicao ja julgada. E a unidade de tudo que o relatorio conta."""

    suite: str
    group: str
    method: str
    path: str
    status: int = 0
    latency_ms: float = 0.0
    expectation: str = ACCEPT
    case: str = "valido"
    error: str = ""
    detail: str = ""
    payload: str = ""
    started_at: float = 0.0
    verdict: str = field(default="", init=False)

    def __post_init__(self):
        self.verdict = classify(self.expectation, self.status, self.error)

    @property
    def is_defect(self):
        return self.verdict in DEFECTS

    def repro(self):
        """Linha curta que permite repetir a requisicao na mao."""
        body = f" -d '{self.payload[:400]}'" if self.payload else ""
        return f"{self.method} {self.path}{body}"
