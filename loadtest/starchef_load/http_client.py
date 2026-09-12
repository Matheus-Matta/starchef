"""Cliente HTTP de carga: keep-alive por thread, sem dependencia externa.

`requests` cria overhead por chamada e nao deixa mandar um corpo proposital-
mente malformado. Aqui usamos `http.client` direto: uma conexao viva por
thread, e a opcao de enviar bytes crus com o content-type que quisermos.
"""
import http.client
import json
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

_local = threading.local()


class Response:
    __slots__ = ("status", "body", "elapsed_ms", "error", "headers")

    def __init__(self, status=0, body=b"", elapsed_ms=0.0, error="", headers=None):
        self.status = status
        self.body = body
        self.elapsed_ms = elapsed_ms
        self.error = error
        self.headers = headers or {}

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except (ValueError, AttributeError):
            return None

    def excerpt(self, limit=220):
        return self.body[:limit].decode("utf-8", "replace").replace("\n", " ")


class HttpClient:
    """Um alvo (base_url). Conexoes sao por thread, entao pode ser compartilhado."""

    def __init__(self, base_url, timeout=20.0):
        parts = urlsplit(base_url)
        self.scheme = parts.scheme or "http"
        self.host = parts.hostname or "localhost"
        self.port = parts.port or (443 if self.scheme == "https" else 80)
        self.prefix = parts.path.rstrip("/")
        self.timeout = timeout
        self.base_url = f"{self.scheme}://{self.host}:{self.port}{self.prefix}"

    def _key(self):
        return f"conn:{self.host}:{self.port}:{self.scheme}"

    def _connection(self):
        conn = getattr(_local, self._key(), None)
        if conn is None:
            if self.scheme == "https":
                conn = http.client.HTTPSConnection(
                    self.host, self.port, timeout=self.timeout, context=ssl._create_unverified_context()
                )
            else:
                conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
            setattr(_local, self._key(), conn)
        return conn

    def drop(self):
        conn = getattr(_local, self._key(), None)
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass
            setattr(_local, self._key(), None)

    def request(self, method, path, body=None, headers=None, raw=None, content_type="application/json"):
        """Uma requisicao. `raw` (bytes) ignora `body` — e o caminho do lixo cru."""
        payload = raw
        if payload is None and body is not None:
            payload = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        sent_headers = {"Accept": "application/json", "Connection": "keep-alive"}
        if payload is not None:
            sent_headers["Content-Type"] = content_type
            sent_headers["Content-Length"] = str(len(payload))
        if headers:
            sent_headers.update({k: v for k, v in headers.items() if v is not None})

        url = f"{self.prefix}{path}"
        started = time.perf_counter()
        for attempt in (1, 2):
            conn = self._connection()
            try:
                conn.request(method, url, body=payload, headers=sent_headers)
                raw_response = conn.getresponse()
                data = raw_response.read()
                return Response(
                    raw_response.status,
                    data,
                    (time.perf_counter() - started) * 1000.0,
                    headers=dict(raw_response.getheaders()),
                )
            except (http.client.HTTPException, socket.timeout, TimeoutError, OSError) as exc:
                self.drop()
                # Keep-alive fechado pelo servidor entre duas requisicoes e
                # normal: uma retentativa distingue isso de servidor caido.
                if attempt == 1 and isinstance(exc, (http.client.BadStatusLine, ConnectionResetError, http.client.RemoteDisconnected)):
                    continue
                return Response(
                    0, b"", (time.perf_counter() - started) * 1000.0, error=f"{type(exc).__name__}: {exc}"
                )
        return Response(0, b"", 0.0, error="sem resposta")
