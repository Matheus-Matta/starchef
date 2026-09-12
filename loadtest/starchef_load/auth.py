"""Sessao autenticada contra a API.

O PDV usa `Authorization: Bearer` (o WS do caixa exige isso, §6 do BACKEND.md),
entao a carga usa o mesmo caminho: sem cookie, sem CSRF, e cada terminal
simulado carrega a propria identidade (`X-Terminal-Id`).
"""
import json
import uuid
from urllib.parse import quote


class AuthError(RuntimeError):
    pass


class Session:
    """Credencial + cabecalhos de um cliente (web, PDV ou aplicativo)."""

    def __init__(self, client, access="", refresh="", user=None, terminal_id="", terminal_name="", role=""):
        self.client = client
        self.access = access
        self.refresh = refresh
        self.user = user or {}
        self.terminal_id = terminal_id or str(uuid.uuid4())
        self.terminal_name = terminal_name or "LT terminal"
        self.role = role

    def headers(self, extra=None, idempotency_key=None):
        headers = {
            "Authorization": f"Bearer {self.access}" if self.access else None,
            "X-Terminal-Id": self.terminal_id,
            "X-Terminal-Name": quote(self.terminal_name),
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if extra:
            headers.update(extra)
        return {k: v for k, v in headers.items() if v is not None}

    def get(self, path, extra=None):
        return self.client.request("GET", path, headers=self.headers(extra))

    def post(self, path, body, extra=None, idempotency_key=None):
        return self.client.request(
            "POST", path, body=body, headers=self.headers(extra, idempotency_key)
        )

    def patch(self, path, body, extra=None):
        return self.client.request("PATCH", path, body=body, headers=self.headers(extra))

    def delete(self, path, body=None, extra=None):
        return self.client.request("DELETE", path, body=body, headers=self.headers(extra))

    def json_get(self, path, extra=None):
        response = self.get(path, extra)
        if response.status != 200:
            return None
        return response.json()


def login(client, username, password, *, terminal_name="LT", terminal_id="", client_kind=""):
    """Autentica e devolve uma `Session`. Falha aqui aborta a suite inteira."""
    body = {"username": username, "password": password}
    if client_kind:
        body["client"] = client_kind
    response = client.request("POST", "/api/v1/auth/login/", body=body)
    if response.status != 200:
        raise AuthError(
            f"login de {username} falhou: HTTP {response.status} {response.excerpt()}"
        )
    data = response.json() or {}
    session = Session(
        client,
        access=data.get("access", ""),
        refresh=data.get("refresh", ""),
        terminal_id=terminal_id,
        terminal_name=terminal_name,
    )
    me = session.json_get("/api/v1/auth/me/")
    if isinstance(me, dict):
        session.user = me
        profile = me.get("profile") or {}
        session.role = (profile.get("role") or {}).get("code", "") if isinstance(profile.get("role"), dict) else ""
    return session


def clone(session, *, terminal_name, terminal_id=""):
    """Outro terminal, mesma credencial — e o caso do PDV secundario."""
    novo = Session(
        session.client,
        access=session.access,
        refresh=session.refresh,
        user=session.user,
        terminal_id=terminal_id or str(uuid.uuid4()),
        terminal_name=terminal_name,
        role=session.role,
    )
    return novo


def describe(session):
    return json.dumps(
        {"usuario": session.user.get("username"), "terminal": session.terminal_name},
        ensure_ascii=False,
    )
