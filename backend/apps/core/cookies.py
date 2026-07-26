"""Helpers reutilizáveis para os cookies de autenticação (tokens JWT).

Os tokens ficam em cookies **httpOnly** (imunes a leitura por JS/XSS). Um cookie
extra `sc_session` (legível) sinaliza ao frontend que há sessão ativa, sem expor
o token. Em produção os cookies são `Secure` (exigem HTTPS).
"""
from django.conf import settings


def _base_kwargs():
    return {
        "domain": getattr(settings, "AUTH_COOKIE_DOMAIN", "") or None,
        "secure": getattr(settings, "AUTH_COOKIE_SECURE", not settings.DEBUG),
        "samesite": getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax"),
        "path": "/",
    }


def _seconds(key, default):
    delta = settings.SIMPLE_JWT.get(key)
    return int(delta.total_seconds()) if delta else default


def set_auth_cookies(response, *, access=None, refresh=None):
    """Grava os cookies httpOnly de access/refresh + a flag de sessão legível."""
    kwargs = _base_kwargs()
    if access is not None:
        response.set_cookie(
            settings.JWT_AUTH_COOKIE, access,
            max_age=_seconds("ACCESS_TOKEN_LIFETIME", 3600), httponly=True, **kwargs,
        )
    if refresh is not None:
        response.set_cookie(
            settings.JWT_AUTH_REFRESH_COOKIE, refresh,
            max_age=_seconds("REFRESH_TOKEN_LIFETIME", 604800), httponly=True, **kwargs,
        )
    response.set_cookie(
        settings.AUTH_SESSION_COOKIE, "1",
        max_age=_seconds("REFRESH_TOKEN_LIFETIME", 604800), httponly=False, **kwargs,
    )
    return response


def clear_auth_cookies(response):
    kwargs = _base_kwargs()
    for name in (settings.JWT_AUTH_COOKIE, settings.JWT_AUTH_REFRESH_COOKIE, settings.AUTH_SESSION_COOKIE):
        response.delete_cookie(name, path=kwargs["path"], domain=kwargs["domain"], samesite=kwargs["samesite"])
    return response
