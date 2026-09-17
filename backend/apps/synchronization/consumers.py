"""O consumer da NUVEM: recebe as conexões dos nós locais.

Ele faz pouco de propósito (§12.3): autentica, valida o envelope, persiste,
responde ACK ou NACK e enfileira. Importação completa e regra pesada rodam no
worker — um consumer que aplica eventos trava a conexão de todo mundo.
"""
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from apps.synchronization.constants import CloseCode, MessageType
from apps.synchronization.consumer_handlers import HandlerMixin
from apps.synchronization.services import authentication, guard, protocol

logger = logging.getLogger(__name__)


class SyncConsumer(HandlerMixin, AsyncWebsocketConsumer):
    """Uma conexão = um nó local autenticado = uma conta. Nunca mais que isso."""

    node = None
    group = None
    key = None

    async def connect(self):
        try:
            guard.ensure_enabled()
        except Exception as erro:  # noqa: BLE001
            logger.warning("sync: conexão recusada — %s", erro)
            await self.close(code=CloseCode.WRONG_ENVIRONMENT)
            return
        # A chave é do AMBIENTE, não do nó — então já está disponível aqui, e
        # precisa estar: o `receive` decifra a mensagem ANTES de saber quem a
        # enviou, e o HELLO já chega cifrado. Defini-la só no `handle_hello`
        # criava um ovo-e-galinha — a nuvem recusava o próprio HELLO com
        # "mensagem cifrada recebida sem chave configurada", e a loja nunca
        # passava do handshake.
        self.key = getattr(settings, "SYNC_ENCRYPTION_KEY", "") or None

        # Aceita sem identidade: quem prova quem é, é o HELLO. Até lá a conexão
        # não está em grupo nenhum e não recebe dado de conta alguma.
        await self.accept()

    async def disconnect(self, code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)
        if self.node is not None:
            await database_sync_to_async(authentication.mark_offline)(
                self.node, f"Conexão encerrada (código {code})."
            )

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            envelope = json.loads(text_data)
        except ValueError:
            await self.send_error("Mensagem não é JSON válido.", code="bad_json")
            return

        tipo = envelope.get("message_type")
        if self.node is None and tipo not in MessageType.PRE_AUTH:
            await self.close(code=CloseCode.UNAUTHENTICATED)
            return

        try:
            payload = await database_sync_to_async(protocol.parse)(envelope, self.key)
        except protocol.ProtocolError as erro:
            # Envelope ruim não derruba a conexão: vira NACK e a origem
            # retenta. Derrubar aqui transformaria um bug de serialização numa
            # loja offline.
            await self.send_error(str(erro), code="protocol_error",
                                  correlation_id=envelope.get("message_id"))
            return

        await self.dispatch_message(tipo, envelope, payload)

    async def dispatch_message(self, tipo, envelope, payload):
        manipulador = {
            MessageType.HELLO: self.handle_hello,
            MessageType.HEARTBEAT: self.handle_heartbeat,
            MessageType.EVENT_BATCH: self.handle_event_batch,
            MessageType.ACK: self.handle_ack,
            MessageType.NACK: self.handle_ack,
            MessageType.SYNC_PULL_REQUEST: self.handle_pull_request,
        }.get(tipo)

        if manipulador is None:
            # Tipo conhecido mas sem tratamento aqui (SNAPSHOT_*, por exemplo,
            # chega como EVENT_BATCH) — registra e segue.
            logger.info("sync: mensagem %s sem tratamento no consumer", tipo)
            return
        await manipulador(envelope, payload)

    # ── envio ────────────────────────────────────────────────────────────────
    async def send_envelope(self, message_type, payload, *, correlation_id=None,
                            sequence_start=None, sequence_end=None):
        envelope = await database_sync_to_async(protocol.build)(
            message_type,
            source_node_id=self.scope.get("sync_self_node_id"),
            target_node_id=self.node.id if self.node else None,
            account_id=self.node.account_id if self.node else None,
            payload=payload,
            key=self.key,
            key_id=self.node.encryption_key_id if self.node else "",
            correlation_id=correlation_id,
            sequence_start=sequence_start,
            sequence_end=sequence_end,
        )
        await self.send(text_data=json.dumps(envelope, default=str))

    async def send_error(self, reason, *, code="error", correlation_id=None):
        await self.send(
            text_data=json.dumps(
                protocol.error_envelope(reason, code=code, correlation_id=correlation_id),
                default=str,
            )
        )

    # ── mensagens vindas do grupo (channel layer) ────────────────────────────
    async def sync_available(self, event):
        """A nuvem avisa que há algo novo para esta loja (§13.2)."""
        await self.send_envelope(MessageType.SYNC_AVAILABLE, event.get("payload", {}))

    async def sync_revoked(self, _event):
        await self.close(code=CloseCode.REVOKED)
