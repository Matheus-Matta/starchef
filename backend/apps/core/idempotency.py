"""Deduplicação de mutações reenviadas pela fila offline do PDV.

O terminal desktop guarda o que não conseguiu enviar e tenta de novo depois.
Uma tentativa pode repetir uma operação que o servidor já processou — a
resposta pode ter se perdido no caminho, ou o token pode ter vencido logo
depois da escrita. Sem deduplicação, esse reenvio vira uma venda duplicada.

O contrato é o mesmo usado pela indústria: o cliente manda `Idempotency-Key`
em requisições de escrita; a primeira execução guarda a resposta junto da
operação, na mesma transação, e as repetições recebem a resposta guardada sem
executar nada.
"""

import hashlib
import json

from django.db import IntegrityError, transaction
from django.http import JsonResponse

HEADER = "Idempotency-Key"

# Somente métodos que criam ou alteram estado. GET e HEAD já são repetíveis.
GUARDED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Autenticação não passa por aqui: o login precisa poder ser repetido, e o
# refresh rotaciona o token a cada chamada.
EXEMPT_PREFIXES = ("/api/v1/auth/", "/admin/")


def _fingerprint(request, body: bytes) -> str:
    raw = b"|".join(
        [
            request.method.encode(),
            request.get_full_path().encode(),
            body or b"",
        ]
    )
    return hashlib.sha256(raw).hexdigest()


class IdempotencyMiddleware:
    """Garante que uma chave execute a operação uma única vez por conta."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = (request.headers.get(HEADER) or "").strip()[:200]
        account = getattr(request, "account", None)
        if (
            not key
            or account is None
            or request.method not in GUARDED_METHODS
            or request.path.startswith(EXEMPT_PREFIXES)
        ):
            return self.get_response(request)

        # `request.body` precisa ser lido antes da view consumir o stream.
        try:
            body = request.body
        except Exception:
            body = b""
        fingerprint = _fingerprint(request, body)

        from apps.core.models import IdempotencyRecord

        stored = IdempotencyRecord.objects.filter(account=account, key=key).first()
        if stored is not None:
            if stored.request_fingerprint != fingerprint:
                # A mesma chave para outra requisição indica erro de cliente;
                # devolver a resposta antiga aqui esconderia o problema.
                return JsonResponse(
                    {
                        "detail": (
                            "Esta chave de idempotência já foi usada para outra operação."
                        )
                    },
                    status=409,
                )
            return self._replay(stored)

        with transaction.atomic():
            response = self.get_response(request)
            if not self._should_record(response):
                return response
            try:
                IdempotencyRecord.objects.create(
                    account=account,
                    key=key,
                    method=request.method,
                    path=request.path[:500],
                    request_fingerprint=fingerprint,
                    status_code=response.status_code,
                    response_body=self._decode(response),
                )
            except IntegrityError:
                # Duas tentativas simultâneas com a mesma chave: a outra venceu
                # a corrida e já gravou. Manter esta resposta é seguro porque
                # ambas descrevem a mesma operação.
                pass
        return response

    @staticmethod
    def _should_record(response) -> bool:
        # Só respostas bem-sucedidas são repetíveis. Guardar um erro impediria
        # o operador de tentar de novo depois de corrigir a causa.
        if not (200 <= response.status_code < 300):
            return False
        return response.get("Content-Type", "").startswith("application/json")

    @staticmethod
    def _decode(response):
        try:
            return json.loads(response.content.decode(response.charset or "utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _replay(stored):
        response = JsonResponse(stored.response_body, safe=False, status=stored.status_code)
        response["Idempotent-Replay"] = "true"
        return response
