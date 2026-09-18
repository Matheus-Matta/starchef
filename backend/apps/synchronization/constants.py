"""Vocabulário fixo do protocolo de sincronização.

Tudo que os dois lados precisam interpretar do mesmo jeito mora aqui: nada
neste arquivo pode mudar de valor sem subir `PROTOCOL_VERSION` — o nó remoto
pode estar numa versão anterior e continuar lendo estas strings.
"""

#: Versão do envelope trocado no WebSocket (ver `services/protocol.py`).
PROTOCOL_VERSION = 1

#: Versão do formato dos payloads de entidade (ver `services/serialization.py`).
SCHEMA_VERSION = 1

#: Ambientes da sincronização. Ver `services/guard.py`.
#:
#: Não são rótulo: o ambiente faz parte da IDENTIDADE do nó e é conferido no
#: HELLO. Uma loja de homologação não consegue conectar na nuvem de produção
#: nem com credencial válida — é o que impede venda de teste entrar no banco
#: que vale, por um `.env` apontado para o lugar errado.
ENVIRONMENT_DEVELOPMENT = "development"
ENVIRONMENT_PRODUCTION = "production"
ENVIRONMENT_CHOICES = [
    (ENVIRONMENT_DEVELOPMENT, "Development"),
    (ENVIRONMENT_PRODUCTION, "Production"),
]
#: Os valores aceitos. Qualquer outra coisa é erro de configuração, não um
#: ambiente novo — um typo em `SYNC_ENVIRONMENT` não pode virar um terceiro
#: ambiente silencioso no qual nenhum nó encontra nenhum outro.
ENVIRONMENTS_ALLOWED = frozenset({ENVIRONMENT_DEVELOPMENT, ENVIRONMENT_PRODUCTION})


class NodeType:
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"
    CHOICES = [(LOCAL, "Servidor da loja"), (CLOUD, "Servidor da nuvem")]


class NodeStatus:
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    OFFLINE = "OFFLINE"
    BLOCKED = "BLOCKED"
    REVOKED = "REVOKED"
    CHOICES = [
        (PENDING, "Aguardando primeiro handshake"),
        (ACTIVE, "Ativo"),
        (OFFLINE, "Sem conexão"),
        (BLOCKED, "Bloqueado"),
        (REVOKED, "Revogado"),
    ]
    #: Estados em que o nó ainda pode abrir conexão.
    CONNECTABLE = {PENDING, ACTIVE, OFFLINE}


class Direction:
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    CHOICES = [(INBOUND, "Recebido"), (OUTBOUND, "Enviado")]


class Operation:
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    UPSERT = "UPSERT"
    SNAPSHOT = "SNAPSHOT"
    CHOICES = [
        (CREATE, "Criação"),
        (UPDATE, "Atualização"),
        (DELETE, "Exclusão"),
        (UPSERT, "Upsert"),
        (SNAPSHOT, "Snapshot"),
    ]


class EventStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    RECEIVED = "RECEIVED"
    APPLIED = "APPLIED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    DEAD = "DEAD"
    CHOICES = [
        (PENDING, "Na fila"),
        (PROCESSING, "Em processamento"),
        (SENT, "Enviado, sem confirmação"),
        (RECEIVED, "Recebido pelo destino"),
        (APPLIED, "Aplicado no destino"),
        (ACKNOWLEDGED, "Confirmado na origem"),
        (FAILED, "Falhou, vai tentar de novo"),
        (DEAD, "Desistiu; exige reprocessamento manual"),
    ]
    #: Ainda precisa de alguma ação do worker de envio.
    OUTBOUND_OPEN = {PENDING, FAILED, SENT, PROCESSING}
    #: Ainda precisa de alguma ação do worker de aplicação.
    INBOUND_OPEN = {RECEIVED, FAILED, PROCESSING}
    #: Chegou ao fim, com sucesso ou não.
    TERMINAL = {ACKNOWLEDGED, DEAD}


class RunType:
    BOOTSTRAP = "BOOTSTRAP"
    FULL = "FULL"
    INCREMENTAL = "INCREMENTAL"
    CHOICES = [(BOOTSTRAP, "Dados essenciais"), (FULL, "Tudo"), (INCREMENTAL, "Incremental")]


class RunStatus:
    PENDING = "PENDING"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    CHOICES = [
        (PENDING, "Na fila"),
        (PREPARING, "Preparando"),
        (RUNNING, "Enviando"),
        (VALIDATING, "Validando"),
        (COMPLETED, "Concluída"),
        (FAILED, "Falhou"),
        (CANCELLED, "Cancelada"),
    ]
    #: Uma carga nestes estados impede outra no mesmo nó.
    BUSY = {PENDING, PREPARING, RUNNING, VALIDATING}


class ConflictResolution:
    CLOUD_WINS = "CLOUD_WINS"
    LOCAL_WINS = "LOCAL_WINS"
    LAST_VERSION = "LAST_VERSION"
    MANUAL = "MANUAL"
    IGNORED = "IGNORED"
    CHOICES = [
        (CLOUD_WINS, "Nuvem vence"),
        (LOCAL_WINS, "Loja vence"),
        (LAST_VERSION, "Maior versão vence"),
        (MANUAL, "Revisão manual"),
        (IGNORED, "Ignorado"),
    ]


class ConflictStatus:
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"
    CHOICES = [(OPEN, "Aberto"), (RESOLVED, "Resolvido"), (IGNORED, "Ignorado")]


class MessageType:
    HELLO = "HELLO"
    AUTHENTICATED = "AUTHENTICATED"
    HEARTBEAT = "HEARTBEAT"
    EVENT_BATCH = "EVENT_BATCH"
    ACK = "ACK"
    NACK = "NACK"
    SYNC_AVAILABLE = "SYNC_AVAILABLE"
    SYNC_PULL_REQUEST = "SYNC_PULL_REQUEST"
    SNAPSHOT_START = "SNAPSHOT_START"
    SNAPSHOT_BATCH = "SNAPSHOT_BATCH"
    SNAPSHOT_COMPLETE = "SNAPSHOT_COMPLETE"
    SNAPSHOT_VALIDATED = "SNAPSHOT_VALIDATED"
    KEY_ROTATION_REQUIRED = "KEY_ROTATION_REQUIRED"
    ERROR = "ERROR"

    #: Mensagens que um nó pode enviar sem ter passado pelo HELLO.
    PRE_AUTH = {HELLO}
    ALL = {
        HELLO, AUTHENTICATED, HEARTBEAT, EVENT_BATCH, ACK, NACK,
        SYNC_AVAILABLE, SYNC_PULL_REQUEST, SNAPSHOT_START, SNAPSHOT_BATCH,
        SNAPSHOT_COMPLETE, SNAPSHOT_VALIDATED, KEY_ROTATION_REQUIRED, ERROR,
    }


#: Códigos de fechamento do WebSocket. Ficam na faixa privada (4000-4999).
class CloseCode:
    UNAUTHENTICATED = 4401
    FORBIDDEN = 4403
    REVOKED = 4404
    PROTOCOL = 4400
    WRONG_ENVIRONMENT = 4412
    INCOMPATIBLE = 4426
    #: Outro processo autenticou com a MESMA identidade de nó e assumiu a vez.
    SUPERSEDED = 4409
