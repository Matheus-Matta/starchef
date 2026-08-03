"""Smoke tests do app core: healthcheck e o fingerprint de idempotência.

Não é cobertura de regra de negócio — é a rede mínima que garante que o
health endpoint (usado pelo healthcheck do docker-compose) e a função pura
de fingerprint continuam funcionando.
"""
from apps.core.idempotency import _fingerprint
from django.test import RequestFactory


def test_health_endpoint_ok(client):
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_fingerprint_is_stable_for_same_request():
    rf = RequestFactory()
    request = rf.post("/api/v1/orders/", data=b'{"a": 1}', content_type="application/json")
    first = _fingerprint(request, request.body)
    second = _fingerprint(request, request.body)
    assert first == second


def test_fingerprint_differs_for_different_body():
    rf = RequestFactory()
    request_a = rf.post("/api/v1/orders/", data=b'{"a": 1}', content_type="application/json")
    request_b = rf.post("/api/v1/orders/", data=b'{"a": 2}', content_type="application/json")
    assert _fingerprint(request_a, request_a.body) != _fingerprint(request_b, request_b.body)
