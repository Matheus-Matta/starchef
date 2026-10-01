"""Terminal do PDV logado não tem limite de requisições; o painel tem."""
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
    # Terminal logado: sem limite — nem a faixa própria (200/h aqui) o barra.
    assert all(tentar(HTTP_X_TERMINAL_ID="pdv-1") for _ in range(500))


@pytest.mark.django_db
def test_terminal_sem_login_continua_limitado(monkeypatch):
    """O cabeçalho sozinho não abre a porta: quem não está logado segue barrado."""
    from django.contrib.auth.models import AnonymousUser
    from rest_framework.request import Request
    from rest_framework.throttling import AnonRateThrottle

    monkeypatch.setattr(AnonRateThrottle, "THROTTLE_RATES", {"anon": "2/hour"})
    cache.clear()
    fabrica = APIRequestFactory()

    def tentar():
        request = fabrica.get("/api/v1/orders/", HTTP_X_TERMINAL_ID="pdv-1")
        force_authenticate(request, user=AnonymousUser())
        return AnonRateThrottle().allow_request(Request(request), _View())

    assert [tentar() for _ in range(3)] == [True, True, False]


@pytest.mark.django_db
def test_login_conta_por_usuario_e_nao_pela_loja_inteira(monkeypatch):
    """Todos os terminais da loja saem pelo MESMO IP público.

    Com o limite do login contado só por IP (10/min), a troca de turno — dez
    aparelhos entrando juntos, um operador errando a senha — esgotava a cota
    da loja inteira, e quem digitava certo recebia 429.
    """
    from rest_framework.request import Request
    from rest_framework.parsers import JSONParser

    from apps.core.throttling import LoginIpRateThrottle, LoginRateThrottle

    monkeypatch.setattr(LoginRateThrottle, "THROTTLE_RATES", {"login": "2/min", "login_ip": "5/min"})
    monkeypatch.setattr(LoginIpRateThrottle, "THROTTLE_RATES", {"login": "2/min", "login_ip": "5/min"})
    cache.clear()
    fabrica = APIRequestFactory()

    def tentar(usuario):
        request = Request(
            fabrica.post("/api/v1/auth/login/", {"username": usuario}, format="json"),
            parsers=[JSONParser()],
        )
        return all(t.allow_request(request, _View()) for t in (LoginRateThrottle(), LoginIpRateThrottle()))

    # A mesma conta segue protegida contra adivinhação de senha...
    assert [tentar("caixa1") for _ in range(3)] == [True, True, False]
    # ...mas o colega no aparelho ao lado entra normalmente.
    assert tentar("Caixa2") is True
    # E o IP tem um teto próprio, mais largo, contra varredura de contas.
    assert [tentar(f"op{i}") for i in range(3)] == [True, True, False]
