"""O cliente WSS do nó LOCAL: a conexão SEMPRE sai da loja.

É o que dispensa a loja de expor porta, IP fixo ou certificado: quem abre a
conexão é ela, para a nuvem. Se a internet cair, a loja continua vendendo e
esta classe só volta a conectar quando puder — os eventos ficam na outbox o
tempo que for preciso.
"""
import asyncio
import json
import logging
import random

import websockets

from apps.synchronization.constants import MessageType, PROTOCOL_VERSION, SCHEMA_VERSION
from apps.synchronization.services import protocol

logger = logging.getLogger(__name__)

BACKOFF_INICIAL = 1.0
BACKOFF_MAXIMO = 60.0


class CloudConnection:
    """Uma conexão viva com a nuvem, com handshake, heartbeat e reconexão."""

    def __init__(self, *, url, token, node_id, pair_id, account_id, key=None,
                 key_id="", app_version="", heartbeat=20.0, open_timeout=15.0):
        self.url = url
        self.token = token
        self.node_id = str(node_id)
        self.pair_id = str(pair_id)
        self.account_id = str(account_id)
        self.key = key or None
        self.key_id = key_id
        self.app_version = app_version
        self.heartbeat = heartbeat
        self.open_timeout = open_timeout
        self.socket = None
        self.peer_node_id = None
        self.authenticated = asyncio.Event()

    @property
    def is_open(self):
        return self.socket is not None and not getattr(self.socket, "closed", True)

    async def connect(self):
        """Abre a conexão e faz o HELLO. Levanta se qualquer etapa falhar."""
        cabecalhos = {"Authorization": f"Bearer {self.token}"}
        self.socket = await websockets.connect(
            self.url,
            additional_headers=cabecalhos,
            open_timeout=self.open_timeout,
            ping_interval=self.heartbeat,
            ping_timeout=self.heartbeat * 2,
            max_size=16 * 1024 * 1024,
        )
        self.authenticated.clear()
        await self.send(MessageType.HELLO, self._hello_payload())
        return self.socket

    def _hello_payload(self):
        return {
            "node_id": self.node_id,
            "pair_id": self.pair_id,
            "account_id": self.account_id,
            "environment": "development",
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": SCHEMA_VERSION,
            "app_version": self.app_version,
        }

    async def send(self, message_type, payload, **kwargs):
        envelope = protocol.build(
            message_type,
            source_node_id=self.node_id,
            target_node_id=self.peer_node_id,
            account_id=self.account_id,
            payload=payload,
            key=self.key,
            key_id=self.key_id,
            **kwargs,
        )
        await self.socket.send(json.dumps(envelope, default=str))
        return envelope

    async def receive(self, timeout=None):
        """Devolve `(tipo, envelope, payload)`. `None` quando o tempo esgota."""
        try:
            bruto = await asyncio.wait_for(self.socket.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        envelope = json.loads(bruto)
        tipo = envelope.get("message_type")
        if tipo == MessageType.ERROR:
            return tipo, envelope, envelope.get("payload", {})
        payload = protocol.parse(envelope, self.key)
        if tipo == MessageType.AUTHENTICATED:
            self.peer_node_id = payload.get("peer_node_id")
            self.authenticated.set()
        return tipo, envelope, payload

    async def close(self):
        if self.socket is not None:
            try:
                await self.socket.close()
            finally:
                self.socket = None
                self.authenticated.clear()


async def backoff_sleep(tentativa):
    """Espera crescente com jitter — cem lojas não voltam no mesmo segundo."""
    base = min(BACKOFF_MAXIMO, BACKOFF_INICIAL * (2 ** min(tentativa, 6)))
    await asyncio.sleep(base * (0.75 + random.random() * 0.5))
