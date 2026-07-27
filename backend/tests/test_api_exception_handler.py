from django.test import RequestFactory

from apps.core.exceptions import api_exception_handler


def test_unhandled_exception_returns_stable_json_envelope():
    request = RequestFactory().get("/api/v1/test/")

    response = api_exception_handler(RuntimeError("sensitive internal detail"), {"request": request})

    assert response.status_code == 500
    assert response.data == {
        "success": False,
        "status_code": 500,
        "error": {
            "code": "internal_error",
            "message": "Ocorreu um erro interno. Tente novamente mais tarde.",
        },
    }
    assert "sensitive internal detail" not in str(response.data)
