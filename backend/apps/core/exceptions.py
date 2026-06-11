from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return response

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

