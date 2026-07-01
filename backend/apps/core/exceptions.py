import logging

from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

logger = logging.getLogger("api.errors")


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)

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

