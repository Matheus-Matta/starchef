"""Configuração da sincronização backend-to-backend.

Importado por `config/settings/base.py`. Duas variáveis decidem o papel desta
instalação, e **elas são as únicas diferenças** entre o backend da loja e o da
nuvem — é a mesma imagem, o mesmo código, as mesmas migrations:

    SYNC_NODE_TYPE=cloud   -> recebe conexões WSS das lojas
    SYNC_NODE_TYPE=local   -> abre a conexão de saída para a nuvem

`SYNC_ENVIRONMENT` só aceita `development` nesta fase. O código recusa
qualquer outro valor (ver `apps/synchronization/services/guard.py`) — não é
uma convenção, é uma exceção levantada.
"""
from pathlib import Path

from decouple import config

SYNC_ENABLED = config("SYNC_ENABLED", default=False, cast=bool)
SYNC_ENVIRONMENT = config("SYNC_ENVIRONMENT", default="development").strip().lower()
SYNC_NODE_TYPE = config("SYNC_NODE_TYPE", default="").strip().lower()

# Identidade desta instalação. Na nuvem, o `sync_provision_node` cria; na loja,
# vêm do pacote gerado pela nuvem e instalados por `sync_install_node`.
SYNC_NODE_ID = config("SYNC_NODE_ID", default="")
SYNC_PAIR_ID = config("SYNC_PAIR_ID", default="")
SYNC_ACCOUNT_ID = config("SYNC_ACCOUNT_ID", default="")
SYNC_STORE_ID = config("SYNC_STORE_ID", default="")
SYNC_PEER_NODE_ID = config("SYNC_PEER_NODE_ID", default="")

# Credenciais. Só o nó LOCAL precisa delas: a nuvem guarda apenas o hash e a
# impressão digital no banco, nunca o segredo em claro.
SYNC_CLOUD_WSS_URL = config("SYNC_CLOUD_WSS_URL", default="")
SYNC_AUTH_TOKEN = config("SYNC_AUTH_TOKEN", default="")
SYNC_ENCRYPTION_KEY = config("SYNC_ENCRYPTION_KEY", default="")
SYNC_ENCRYPTION_KEY_ID = config("SYNC_ENCRYPTION_KEY_ID", default="")

# Lote: um teto por quantidade e outro por bytes. O que estourar primeiro corta
# o lote — um pedido com cem itens não pode virar uma mensagem de 20 MB.
SYNC_BATCH_MAX_EVENTS = config("SYNC_BATCH_MAX_EVENTS", default=200, cast=int)
SYNC_BATCH_MAX_BYTES = config("SYNC_BATCH_MAX_BYTES", default=1048576, cast=int)

# Retenção: só apaga evento JÁ CONFIRMADO pelo outro lado. O que falhou fica.
SYNC_RETENTION_DAYS = config("SYNC_RETENTION_DAYS", default=30, cast=int)

SYNC_APP_VERSION = config("SYNC_APP_VERSION", default="")

#: Filas Celery da sincronização (§12). Separadas para que uma carga total não
#: fique atrás de mil retentativas na mesma fila.
SYNC_CELERY_QUEUES = (
    "sync.dispatch", "sync.receive", "sync.apply", "sync.bootstrap",
    "sync.retry", "sync.reconcile", "sync.cleanup",
)

#: Periódicas. Entram no CELERY_BEAT_SCHEDULE só quando SYNC_ENABLED.
SYNC_BEAT_SCHEDULE = {
    "sync-retry-failed-events": {
        "task": "sync.retry_failed_events",
        "schedule": 30.0,
    },
    "sync-apply-pending-events": {
        "task": "sync.apply_pending_events",
        "schedule": 15.0,
    },
    "sync-notify-pending": {
        "task": "sync.notify_pending_to_local_nodes",
        "schedule": 10.0,
    },
    "sync-reconcile-nodes": {
        "task": "sync.reconcile_nodes",
        "schedule": 60.0,
    },
    "sync-prune-acknowledged": {
        "task": "sync.prune_acknowledged_events",
        "schedule": 6 * 60 * 60.0,
    },
    # A rede de segurança do §11.2. No dia a dia não acha nada — e é esse o
    # resultado esperado. Ela existe para o dia em que alguém rodar um
    # `QuerySet.update()` em mil produtos.
    "sync-collect-dirty-rows": {
        "task": "sync.collect_dirty_rows",
        "schedule": 10.0,
    },
    "sync-prune-dirty-rows": {
        "task": "sync.prune_dirty_rows",
        "schedule": 12 * 60 * 60.0,
    },
    # Fila endereçada a nó que não responde tem prazo. Uma vez por dia basta:
    # o que ela corrige leva dias para aparecer, não segundos.
    "sync-expire-stale-queues": {
        "task": "sync.expire_stale_queues",
        "schedule": 24 * 60 * 60.0,
    },
}


# ── Prazo de validade da fila de saída ───────────────────────────────────────
# Um nó que nunca conectou, ou que emudeceu, acumula fila para sempre. Foi
# assim que centenas de eventos ficaram endereçados à ficha de uma loja que
# rematriculou e passou a conectar por outra — sem erro, sem tentativa, sem
# prazo.
#
# Descartar a fila de SAÍDA não perde nada: ela é regenerável a partir do
# estado atual do banco, e uma carga nova traz dados mais recentes que os
# guardados. A fila de ENTRADA nunca é tocada: aquilo é venda que a loja
# mandou e este lado ainda não aplicou.
SYNC_STALE_NEVER_SEEN_DAYS = config("SYNC_STALE_NEVER_SEEN_DAYS", default=7, cast=int)
SYNC_STALE_SILENT_DAYS = config("SYNC_STALE_SILENT_DAYS", default=30, cast=int)


# ── Matrícula automática do nó LOCAL (primeiro contato) ──────────────────────
# Uma instalação nova não tem token nem banco. Com estas variáveis, o
# `sync_worker` se matricula sozinho na primeira subida: apresenta usuário,
# senha e conta, recebe o pacote de credenciais CIFRADO com o segredo de
# matrícula e a nuvem já enfileira a carga total.
#
# O segredo de matrícula NÃO é a chave de sincronização: ele protege apenas o
# pacote que traz a chave definitiva, que nasce na nuvem. Confundir os dois
# transformaria um segredo digitado por uma pessoa na chave de todo o tráfego.
SYNC_AUTO_ENROLL = config("SYNC_AUTO_ENROLL", default=False, cast=bool)
SYNC_CLOUD_API_URL = config("SYNC_CLOUD_API_URL", default="").rstrip("/")
SYNC_ENROLL_USERNAME = config("SYNC_ENROLL_USERNAME", default="")
SYNC_ENROLL_PASSWORD = config("SYNC_ENROLL_PASSWORD", default="")
SYNC_ENROLL_SECRET = config("SYNC_ENROLL_SECRET", default="")
SYNC_NODE_NAME = config("SYNC_NODE_NAME", default="")
# Onde gravar as credenciais recebidas. Sem isto elas valem só para o processo
# atual — o container reinicia e a loja perde o token.
SYNC_ENROLL_ENV_PATH = config("SYNC_ENROLL_ENV_PATH", default="")


def _carregar_credenciais_da_matricula():
    """Lê de volta o que a matrícula gravou, preenchendo o que veio vazio.

    Gravar o arquivo não bastava: nada o lia. O efeito era que TODO restart do
    container reencontrava `SYNC_AUTH_TOKEN` vazio, concluía "não estou
    matriculado" e se matriculava de novo — gastando uma das 5 tentativas por
    hora, rotacionando a credencial (invalidando a anterior) e disparando mais
    uma carga total. Um `docker compose restart` custava tudo isso.

    Precedência: o que está EXPLÍCITO no ambiente vence. Quem provisionou à mão
    e colou o pacote no `.env` não pode ter esses valores sobrescritos por um
    arquivo de uma matrícula antiga. O arquivo só preenche o que está vazio.
    """
    caminho = SYNC_ENROLL_ENV_PATH
    if not caminho:
        return {}
    arquivo = Path(caminho)
    if not arquivo.is_file():
        return {}

    valores = {}
    try:
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            valores[chave.strip()] = valor.strip()
    except OSError:
        # Arquivo ilegível não pode impedir o backend de subir: sem ele a
        # instalação apenas volta a se comportar como não matriculada.
        return {}
    return valores


_credenciais = _carregar_credenciais_da_matricula()
for _chave in (
    "SYNC_NODE_ID", "SYNC_PAIR_ID", "SYNC_ACCOUNT_ID", "SYNC_STORE_ID",
    "SYNC_PEER_NODE_ID", "SYNC_CLOUD_WSS_URL", "SYNC_AUTH_TOKEN",
    "SYNC_ENCRYPTION_KEY", "SYNC_ENCRYPTION_KEY_ID",
):
    if not globals().get(_chave) and _credenciais.get(_chave):
        globals()[_chave] = _credenciais[_chave]


# ── Arquivos (§16) e métricas (§19.1) ────────────────────────────────────────
# Teto do binário aceito por transferência. Um upload de 2 GB por engano enche
# o disco da loja antes de alguém perceber.
SYNC_FILE_MAX_BYTES = config("SYNC_FILE_MAX_BYTES", default=64 * 1024 * 1024, cast=int)
# Token de raspagem do /api/v1/sync/metrics/. Vazio = só superusuário acessa.
# A rota NUNCA fica aberta, com ou sem token.
SYNC_METRICS_TOKEN = config("SYNC_METRICS_TOKEN", default="")
