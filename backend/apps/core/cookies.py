"""Helpers reutilizáveis para os cookies de autenticação (tokens JWT).

Os tokens ficam em cookies **httpOnly** (imunes a leitura por JS/XSS). Um cookie
extra legível (`sc_session` / `sf_session`) sinaliza ao frontend que há sessão
ativa, sem expor o token. Em produção os cookies são `Secure` (exigem HTTPS).

**Dois escopos, dois conjuntos de nomes.** O painel administrativo e o editor do
storefront batem no MESMO backend, logo os cookies caem no mesmo domínio. Se os
dois usassem `sc_access`, entrar no editor derrubaria a sessão do painel aberta
na outra aba — e, pior, com o usuário errado: o editor passaria a agir como o
operador do painel, ou o contrário. Nomes distintos por escopo eliminam a
colisão; quem escolhe qual escopo ler é o header `X-Auth-Scope`
(ver `apps.core.authentication.CookieJWTAuthentication`).
"""
from django.conf import settings

SCOPE_PANEL = "panel"
SCOPE_STOREFRONT = "storefront"

# escopo -> (setting do access, setting do refresh, setting da flag legível)
_SCOPE_SETTINGS = {
    SCOPE_PANEL: ("JWT_AUTH_COOKIE", "JWT_AUTH_REFRESH_COOKIE", "AUTH_SESSION_COOKIE"),
    SCOPE_STOREFRONT: (
        "STOREFRONT_JWT_AUTH_COOKIE",
        "STOREFRONT_JWT_REFRESH_COOKIE",
        "STOREFRONT_AUTH_SESSION_COOKIE",
    ),
}


def cookie_names(scope=SCOPE_PANEL):
    """Nomes dos três cookies do escopo. Escopo desconhecido cai no painel.

    A leitura é feita na chamada, e não na importação, porque os nomes vêm de
    `settings` — congelá-los no import quebraria os testes que sobrescrevem
    configuração com `override_settings`.
    """
    access, refresh, session = _SCOPE_SETTINGS.get(scope) or _SCOPE_SETTINGS[SCOPE_PANEL]
    return getattr(settings, access), getattr(settings, refresh), getattr(settings, session)


def access_cookie_name(scope=SCOPE_PANEL):
    return cookie_names(scope)[0]


def refresh_cookie_name(scope=SCOPE_PANEL):
    return cookie_names(scope)[1]


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


def set_auth_cookies(response, *, access=None, refresh=None, scope=SCOPE_PANEL):
    """Grava os cookies httpOnly de access/refresh + a flag de sessão legível."""
    kwargs = _base_kwargs()
    access_name, refresh_name, session_name = cookie_names(scope)
    if access is not None:
        response.set_cookie(
            access_name, access,
            max_age=_seconds("ACCESS_TOKEN_LIFETIME", 3600), httponly=True, **kwargs,
        )
    if refresh is not None:
        response.set_cookie(
            refresh_name, refresh,
            max_age=_seconds("REFRESH_TOKEN_LIFETIME", 604800), httponly=True, **kwargs,
        )
    response.set_cookie(
        session_name, "1",
        max_age=_seconds("REFRESH_TOKEN_LIFETIME", 604800), httponly=False, **kwargs,
    )
    return response


def clear_auth_cookies(response, *, scope=SCOPE_PANEL):
    kwargs = _base_kwargs()
    for name in cookie_names(scope):
        response.delete_cookie(name, path=kwargs["path"], domain=kwargs["domain"], samesite=kwargs["samesite"])
    return response
