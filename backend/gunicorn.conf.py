"""Configuração do Gunicorn para produção.

O app é ASGI (Django + Channels), então usamos o UvicornWorker, que serve HTTP e
WebSocket no mesmo processo. Valores sensíveis vêm de env para ajuste sem rebuild.
"""
import multiprocessing
import os

# Endereço de escuta (nginx faz proxy para cá).
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Nº de workers. Default: 2*CPU+1, mas configurável (VPS pequena quer menos).
_default_workers = multiprocessing.cpu_count() * 2 + 1
workers = int(os.getenv("GUNICORN_WORKERS", str(_default_workers)))

# UvicornWorker: obrigatório para ASGI/WebSocket. Sem ele, o WS não sobe.
worker_class = "uvicorn.workers.UvicornWorker"

# Reciclagem de workers evita vazamento de memória em processos longos.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100"))

timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# Logs em stdout/stderr (coletados pelo Docker/agregador).
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
