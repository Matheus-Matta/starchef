import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("api.errors")


def _django_validation_detail(exc):
    """Extrai a mensagem de um django.core.exceptions.ValidationError."""
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    messages = getattr(exc, "messages", None) or [str(exc)]
    return {"detail": " ".join(messages)}


def _integrity_message(exc):
    """Traduz violações comuns de integridade em mensagens compreensíveis."""
    text = str(exc).lower()
    if "unique" in text or "duplicate" in text:
        return "Já existe um registro com estes dados (valor duplicado)."
    if "foreign key" in text or "violates foreign key" in text:
        return "Registro relacionado inválido ou inexistente."
    if "not null" in text or "null value" in text:
        return "Um campo obrigatório não foi informado."
    return "Não foi possível salvar: conflito de integridade dos dados."


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)

    # Violações de integridade do banco (ex.: nome/código duplicado por causa de
    # UniqueConstraint que envolve campos preenchidos no servidor) não são tratadas
    # pelo handler padrão do DRF e virariam um 500 silencioso. Convertemos em 409.
    if response is None and isinstance(exc, IntegrityError):
        response = Response(
            {"detail": _integrity_message(exc)},
            status=status.HTTP_409_CONFLICT,
        )
        setattr(exc, "default_code", "conflict")

    # Serviços de domínio levantam django.core.exceptions.ValidationError (ex.:
    # "Table already has an open order."). O handler padrão do DRF não trata isso
    # e viraria um 500. Convertemos em 400 com mensagem clara.
    if response is None and isinstance(exc, DjangoValidationError):
        response = Response(_django_validation_detail(exc), status=status.HTTP_400_BAD_REQUEST)
        setattr(exc, "default_code", "invalid")

    if response is None:
        return response

    request = context.get("request")
    view = context.get("view")

    if response.status_code >= 400:
        view_name = type(view).__name__ if view else "unknown"
        method = request.method if request else "?"
        path = request.path if request else "?"

        log_data = {
            "view": view_name,
            "method": method,
            "path": path,
            "status": response.status_code,
            "errors": response.data,
        }

        if isinstance(exc, ValidationError):
            logger.warning("Validation error", extra=log_data)
        else:
            logger.error("API error: %s", exc, extra=log_data)

    detail = response.data
    response.data = {
        "success": False,
        "status_code": response.status_code,
        "error": {
            "code": getattr(exc, "default_code", "error"),
            "message": detail,
        },
    }
    return response

