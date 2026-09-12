"""Todo erro sob /api/ sai no mesmo envelope, venha de onde vier."""
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core.envelope import envelope, is_enveloped

pytestmark = pytest.mark.django_db


def _login(client, django_user_model):
    user = django_user_model.objects.create_user(username="env", password="x")
    client.force_authenticate(user)
    return user


def test_rota_inexistente_na_api_responde_json_e_nao_html(django_user_model):
    client = APIClient()
    _login(client, django_user_model)
    resp = client.patch("/api/v1/orders/open-command/0d5716c4-c5f5-45e0-adf0-856d47d03ed2/", {}, format="json")
    assert resp.status_code == 404
    assert resp["Content-Type"].startswith("application/json")
    body = resp.json()
    assert is_enveloped(body)
    assert body["error"]["code"] == "not_found"


def test_detail_solto_vira_mensagem_do_envelope():
    client = APIClient()
    # Sem conta/autenticacao: o middleware de tenant responde JsonResponse({"detail": ...}).
    resp = client.get("/api/v1/menu/products/")
    assert resp.status_code in (401, 403)
    body = resp.json()
    assert is_enveloped(body)
    assert isinstance(body["error"]["message"], str)


def test_erro_ja_envelopado_nao_e_envelopado_de_novo():
    body = envelope(400, {"campo": ["msg"]})
    assert is_enveloped(body)
    assert body["error"]["message"] == {"campo": ["msg"]}
    assert not is_enveloped({"detail": "x"})


@override_settings(DEBUG=False)
def test_html_do_django_fora_da_api_nao_e_tocado():
    client = APIClient()
    resp = client.get("/rota/que/nao/existe/")
    assert resp.status_code == 404
    assert not resp["Content-Type"].startswith("application/json")


def test_corpo_estruturado_entra_inteiro_em_error(django_user_model):
    """O 409 de caixa ocupado traz `code`, `message` e `session`: a tela monta o
    aviso com esses dados, entao eles sobrevivem dentro de `error`."""
    from django.http import JsonResponse

    from apps.core.envelope import ApiErrorEnvelopeMiddleware

    def view(request):
        return JsonResponse({"code": "cash_session_conflict", "message": "ocupado", "session": {"id": "s1"}}, status=409)

    from django.test import RequestFactory

    resp = ApiErrorEnvelopeMiddleware(view)(RequestFactory().post("/api/v1/cash-register/open/"))
    body = __import__("json").loads(resp.content)
    assert body["status_code"] == 409
    assert body["error"] == {"code": "cash_session_conflict", "message": "ocupado", "session": {"id": "s1"}}


def test_banco_indisponivel_e_503_nao_500():
    """Pool esgotado / banco fora durante a view: sobrecarga, nao defeito.
    503 com Retry-After — o PDV reenfileira e o monitoramento nao conta 500."""
    from django.db import OperationalError

    from apps.core import exceptions as handler

    request = type("R", (), {"method": "GET", "path": "/api/v1/x/"})()
    resp = handler.api_exception_handler(OperationalError("couldn't get a connection"), {"request": request, "view": None})
    assert resp.status_code == 503
    assert resp["Retry-After"] == "2"
    assert resp.data["error"]["code"] == "service_unavailable"


def test_banco_indisponivel_ao_autenticar_e_503(monkeypatch):
    from django.db import OperationalError

    from apps.core.middleware import TenantMiddleware

    middleware = TenantMiddleware(lambda request: None)
    monkeypatch.setattr(middleware.jwt_authentication, "authenticate", lambda request: (_ for _ in ()).throw(OperationalError("pool")))
    from django.test import RequestFactory

    request = RequestFactory().get("/api/v1/menu/products/", HTTP_AUTHORIZATION="Bearer x")
    resp = middleware(request)
    assert resp.status_code == 503
    assert resp["Retry-After"] == "2"
