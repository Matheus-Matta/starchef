"""Um formato de erro so para toda a API.

O `api_exception_handler` envelopa o que sai como excecao do DRF em
`{success, status_code, error: {code, message}}`. Mas tres coisas escapavam
dele e chegavam ao cliente em outro formato:

- `return Response({"detail": ...}, status=400)` direto na view (dezenas);
- `JsonResponse({"detail": ...})` dos middlewares de tenant e idempotencia;
- URL de API que nao existe: o Django responde a pagina HTML de 404 — e um
  PATCH em `/orders/open-command/<id>/` recebia `<!DOCTYPE html>`.

Este middleware, o mais externo, garante que TODA resposta >= 400 sob `/api/`
saia envelopada, sem tocar nas views. `response.data` (o que os testes leem)
continua igual; so os bytes mudam.
"""
import json
import logging

from django.http import JsonResponse

logger = logging.getLogger(__name__)

API_PREFIX = "/api/"

#: Codigo e mensagem por status, para respostas que nao trouxeram os seus.
STATUS_INFO = {
    400: ("bad_request", "Requisição inválida."),
    401: ("not_authenticated", "Autenticação necessária."),
    403: ("permission_denied", "Sem permissão para esta ação."),
    404: ("not_found", "Rota ou registro não encontrado."),
    405: ("method_not_allowed", "Método não permitido nesta rota."),
    409: ("conflict", "Conflito com o estado atual do registro."),
    415: ("unsupported_media_type", "Tipo de conteúdo não suportado."),
    429: ("throttled", "Muitas requisições. Aguarde e tente novamente."),
    500: ("internal_error", "Ocorreu um erro interno. Tente novamente mais tarde."),
}


def _info(status_code):
    if status_code in STATUS_INFO:
        return STATUS_INFO[status_code]
    return ("server_error" if status_code >= 500 else "error", "Não foi possível concluir a operação.")


def envelope(status_code, message=None, code=None):
    default_code, default_message = _info(status_code)
    return {
        "success": False,
        "status_code": status_code,
        "error": {"code": code or default_code, "message": message if message is not None else default_message},
    }


def is_enveloped(payload):
    return isinstance(payload, dict) and "success" in payload and "error" in payload


def _is_json(response):
    return response.get("Content-Type", "").startswith("application/json")


class ApiErrorEnvelopeMiddleware:
    """Envelopa qualquer erro sob `/api/` que tenha saido em outro formato."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code < 400 or not request.path.startswith(API_PREFIX):
            return response
        if getattr(response, "streaming", False) or not hasattr(response, "content"):
            return response
        if _is_json(response):
            return self._wrap_json(response)
        return self._replace_non_json(request, response)

    def _wrap_json(self, response):
        try:
            payload = json.loads(response.content.decode(response.charset or "utf-8"))
        except Exception:
            return response
        if is_enveloped(payload):
            return response
        # `{"detail": "..."}` vira mensagem simples; `{"campo": "..."}` fica como
        # esta dentro de `message`, que e como o handler do DRF ja entrega os
        # erros de campo. Um corpo ja estruturado (`code` + `message` + extras,
        # como o 409 de caixa ocupado com `session`) entra inteiro em `error`,
        # para a tela continuar montando o aviso com os dados.
        if isinstance(payload, dict) and set(payload) == {"detail"}:
            body = envelope(response.status_code, payload["detail"])
        elif isinstance(payload, dict) and isinstance(payload.get("code"), str) and "message" in payload:
            body = envelope(response.status_code, payload["message"], payload["code"])
            body["error"].update({k: v for k, v in payload.items() if k not in ("code", "message")})
        else:
            body = envelope(response.status_code, payload)
        body = json.dumps(body, ensure_ascii=False)
        response.content = body.encode(response.charset or "utf-8")
        response["Content-Length"] = str(len(response.content))
        return response

    def _replace_non_json(self, request, response):
        # HTML do Django (404 de rota, 500 fora do DRF): nunca deve chegar a um
        # cliente de API. Os cabecalhos que importam (CORS, cookies) ficam.
        if response.status_code >= 500:
            logger.error("Erro nao-JSON na API", extra={"path": request.path, "status": response.status_code})
        replacement = JsonResponse(envelope(response.status_code), status=response.status_code)
        for header in ("Allow", "Set-Cookie", "Access-Control-Allow-Origin", "Access-Control-Allow-Credentials"):
            if response.has_header(header):
                replacement[header] = response[header]
        return replacement
