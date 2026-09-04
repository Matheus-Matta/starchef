from http.cookies import SimpleCookie
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication


@database_sync_to_async
def get_user_from_token(token):
    if not token:
        return AnonymousUser()

    authenticator = JWTAuthentication()
    try:
        validated = authenticator.get_validated_token(token)
        return authenticator.get_user(validated)
    except Exception:
        return AnonymousUser()


def _token_from_scope(scope):
    """Lê JWT do Bearer nativo, cookie web ou `?token=` legado."""
    headers = dict(scope.get("headers", []))
    authorization = headers.get(b"authorization", b"").decode().strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token

    raw_cookie = headers.get(b"cookie", b"").decode()
    if raw_cookie:
        jar = SimpleCookie()
        try:
            jar.load(raw_cookie)
        except Exception:
            jar = {}
        morsel = jar.get(settings.JWT_AUTH_COOKIE)
        if morsel:
            return morsel.value

    query_string = scope.get("query_string", b"").decode()
    return parse_qs(query_string).get("token", [None])[0]


class JwtAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        scope["user"] = await get_user_from_token(_token_from_scope(scope))
        return await super().__call__(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(inner)
