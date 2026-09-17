"""O laço do worker de sincronização do nó LOCAL.

Processo separado do gunicorn de propósito (§4.3): a loja precisa continuar
vendendo enquanto este laço tenta, falha e tenta de novo. Nada do que ele faz
bloqueia uma venda, e nada que uma venda faça depende dele estar no ar.

O ciclo é: conectar → HELLO → (enviar pendentes | aplicar recebidos |
heartbeat) → se cair, dormir com backoff e recomeçar. Como o estado mora todo
no PostgreSQL, matar este processo no meio de um lote não perde nada.
"""
import asyncio
import logging

from asgiref.sync import sync_to_async

from apps.synchronization.constants import MessageType
from apps.synchronization.services import dispatch, transport
from apps.synchronization.worker_steps import (
    aplicar_recebidos,
    enviar_pendentes,
    registrar_lote_recebido,
    tratar_ack,
)

logger = logging.getLogger(__name__)


class LocalSyncWorker:
    """O worker da loja. Um por instalação; concorrência interna é desnecessária."""

    def __init__(self, *, config, intervalo=2.0, heartbeat=20.0, once=False):
        self.config = config
        self.intervalo = intervalo
        self.heartbeat = heartbeat
        self.once = once
        self.parar = asyncio.Event()

    async def run(self):
        tentativa = 0
        while not self.parar.is_set():
            conexao = transport.CloudConnection(**self.config, heartbeat=self.heartbeat)
            try:
                await conexao.connect()
                await self._esperar_autenticacao(conexao)
                logger.info("sync: autenticado na nuvem (nó %s)", conexao.node_id)
                tentativa = 0
                await self._sessao(conexao)
            except Exception as erro:  # noqa: BLE001 — cair é esperado; desistir não
                logger.warning("sync: sessão encerrada (%s). Reconectando…", erro)
            finally:
                await conexao.close()

            if self.once or self.parar.is_set():
                break
            tentativa += 1
            await transport.backoff_sleep(tentativa)

    async def _esperar_autenticacao(self, conexao, timeout=20.0):
        fim = asyncio.get_event_loop().time() + timeout
        while not conexao.authenticated.is_set():
            if asyncio.get_event_loop().time() > fim:
                raise TimeoutError("A nuvem não respondeu ao HELLO.")
            recebido = await conexao.receive(timeout=timeout)
            if recebido is None:
                continue
            tipo, _envelope, payload = recebido
            if tipo == MessageType.ERROR:
                raise PermissionError(payload.get("reason", "Handshake recusado."))

    async def _sessao(self, conexao):
        """Enquanto a conexão viver: escuta e empurra o que estiver pendente."""
        escuta = asyncio.create_task(self._escutar(conexao))
        empurra = asyncio.create_task(self._empurrar(conexao))
        pulso = asyncio.create_task(self._pulsar(conexao))
        try:
            await asyncio.wait(
                [escuta, empurra, pulso], return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for tarefa in (escuta, empurra, pulso):
                tarefa.cancel()

    async def _escutar(self, conexao):
        while not self.parar.is_set():
            recebido = await conexao.receive(timeout=self.heartbeat * 3)
            if recebido is None:
                continue
            tipo, envelope, payload = recebido
            await self._tratar(conexao, tipo, envelope, payload)

    async def _tratar(self, conexao, tipo, envelope, payload):
        if tipo == MessageType.EVENT_BATCH:
            ids = await sync_to_async(registrar_lote_recebido)(payload, conexao.peer_node_id)
            await conexao.send(
                MessageType.ACK,
                {"received": [str(e.get("event_id")) for e in payload.get("events", [])]},
                correlation_id=envelope.get("message_id"),
            )
            aplicados = await sync_to_async(aplicar_recebidos)(ids)
            if aplicados:
                await conexao.send(MessageType.ACK, {"acknowledged": aplicados})
        elif tipo in (MessageType.ACK, MessageType.NACK):
            await sync_to_async(tratar_ack)(payload, conexao.peer_node_id)
        elif tipo == MessageType.SYNC_AVAILABLE:
            await conexao.send(MessageType.SYNC_PULL_REQUEST, {})
        elif tipo == MessageType.ERROR:
            logger.error("sync: a nuvem respondeu ERROR — %s", payload.get("reason"))

    async def _empurrar(self, conexao):
        """Envia a outbox. Vazia, dorme; cheia, manda lote atrás de lote."""
        while not self.parar.is_set():
            enviados = await sync_to_async(enviar_pendentes)(conexao)
            if enviados:
                lote, corpo, primeiro, ultimo = enviados
                await conexao.send(
                    MessageType.EVENT_BATCH, {"events": corpo},
                    sequence_start=primeiro, sequence_end=ultimo,
                )
                await sync_to_async(dispatch.mark_sent)(lote)
                continue
            if self.once:
                return
            await asyncio.sleep(self.intervalo)

    async def _pulsar(self, conexao):
        while not self.parar.is_set():
            await asyncio.sleep(self.heartbeat)
            await conexao.send(MessageType.HEARTBEAT, {})

    def stop(self):
        self.parar.set()
