"""Terminal do PDV tem faixa própria (100x) de requisições; o painel não."""
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.throttling import TerminalAwareUserRateThrottle


class _View:
    pass


@pytest.mark.django_db
def test_terminal_usa_a_faixa_larga_e_o_painel_a_comum(monkeypatch):
    monkeypatch.setattr(
        TerminalAwareUserRateThrottle, "THROTTLE_RATES", {"user": "2/hour", "terminal_user": "200/hour"}
    )
    cache.clear()
    user = get_user_model().objects.create_user("caixa", password="x")
    fabrica = APIRequestFactory()

    def tentar(**headers):
        request = fabrica.get("/api/v1/orders/", **headers)
        force_authenticate(request, user=user)
        from rest_framework.request import Request

        return TerminalAwareUserRateThrottle().allow_request(Request(request), _View())

    # Painel: estoura no terceiro pedido.
    assert [tentar() for _ in range(3)] == [True, True, False]
    # Terminal: faixa própria, contada à parte — o painel no teto não o barra.
    assert all(tentar(HTTP_X_TERMINAL_ID="pdv-1") for _ in range(50))
