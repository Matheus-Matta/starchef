"""Os tratadores de cada mensagem do consumer da nuvem.

Vivem fora de `consumers.py` para que aquele arquivo continue sendo só o
esqueleto da conexão. Todo acesso a banco aqui passa por
`database_sync_to_async` — o consumer é assíncrono e uma consulta síncrona no
loop de eventos trava a conexão de todos os nós.
"""
import logging

from channels.db import database_sync_to_async
from django.utils import timezone

from apps.synchronization.constants import CloseCode, MessageType, PROTOCOL_VERSION, SCHEMA_VERSION
from apps.synchronization.services import authentication, dispatch, inbox, nodes

logger = logging.getLogger(__name__)


class HandlerMixin:
    async def handle_hello(self, envelope, payload):
        """Autentica e amarra a conexão a UMA conta e UM nó (§9.1)."""
        token = self._token_do_scope()
        try:
            no = await database_sync_to_async(authentication.authenticate)(
                payload, raw_token=token, client_ip=self._client_ip()
            )
        except authentication.AuthenticationFailed as erro:
            logger.warning("sync: HELLO recusado — %s", erro)
            await self.send_error(str(erro), code="unauthenticated")
            await self.close(code=CloseCode.UNAUTHENTICATED)
            return

        self.node = no
        # `self.key` já foi definida no `connect` — ela é do ambiente, não do
        # nó, e o HELLO que acabou de ser lido já veio cifrado com ela.
        self.group = no.group_name
        proprio = await database_sync_to_async(nodes.self_node)()
        self.scope["sync_self_node_id"] = str(proprio.id)

        # UMA conexão por nó. Antes de entrar no grupo, avisa quem já estiver
        # nele com esta identidade que a vez passou.
        #
        # Duas conexões com o mesmo `node_id` não são um cenário exótico: é o
        # que acontece quando alguém clona a instalação da loja (copiar a VM, o
        # volume ou o diretório de credenciais para "subir uma segunda loja
        # rápido"). As duas autenticam, as duas recebem eventos endereçados
        # àquele nó, e cada uma aplica um pedaço — a fila esvazia e nenhuma das
        # duas lojas fica com o banco inteiro. O sintoma aparece dias depois
        # como "faltam pedidos", e a causa é impossível de adivinhar.
        #
        # Deslocar em vez de recusar é deliberado: o caso COMUM aqui não é
        # clonagem, é reconexão — a loja caiu, a nuvem ainda não percebeu, e a
        # conexão velha é um fantasma. Recusar a nova deixaria a loja fora do
        # ar até o timeout da antiga expirar.
        await self.channel_layer.group_send(
            self.group,
            {"type": "sync.displace", "channel": self.channel_name,
             "ip": str(self._client_ip() or "")},
        )
        await self.channel_layer.group_add(self.group, self.channel_name)

        # Reconexão: o que saiu daqui e ninguém confirmou volta para a fila.
        await database_sync_to_async(dispatch.resend_unconfirmed)(proprio)

        await self.send_envelope(
            MessageType.AUTHENTICATED,
            {
                "node_id": str(no.id),
                "pair_id": str(no.pair_id),
                "account_id": str(no.account_id),
                "peer_node_id": str(proprio.id),
                "protocol_version": PROTOCOL_VERSION,
                "schema_version": SCHEMA_VERSION,
                "environment": no.environment,
                "last_received_cursor": no.last_received_cursor,
                "last_sent_cursor": no.last_sent_cursor,
            },
            correlation_id=envelope.get("message_id"),
        )

    async def sync_displace(self, event):
        """Outra conexão assumiu esta identidade de nó. Esta sai."""
        if event.get("channel") == self.channel_name:
            return  # a mensagem é nossa; o group_send alcança quem enviou
        logger.error(
            "sync: nó %s reautenticou de %s enquanto outra conexão estava de pé — "
            "a anterior foi encerrada. Se as duas forem simultâneas e de origens "
            "diferentes, a instalação foi clonada.",
            getattr(self.node, "id", "?"), event.get("ip") or "origem desconhecida",
        )
        await self.close(code=CloseCode.SUPERSEDED)

    async def handle_heartbeat(self, envelope, _payload):
        await database_sync_to_async(self._tocar_presenca)()
        await self.send_envelope(
            MessageType.HEARTBEAT,
            {"server_time": timezone.now().isoformat()},
            correlation_id=envelope.get("message_id"),
        )

    async def handle_event_batch(self, envelope, payload):
        """Persiste o lote e só então responde. Nunca o contrário (§10.3)."""
        eventos = payload.get("events") or []
        try:
            aceitos, maior = await database_sync_to_async(inbox.store_batch)(
                eventos, connection_node=self.node, account_id=self.node.account_id
            )
        except inbox.CrossTenantRejected as erro:
            logger.error("sync: lote cross-tenant recusado node=%s", self.node.id)
            await self.send_error(str(erro), code="cross_tenant",
                                  correlation_id=envelope.get("message_id"))
            await self.close(code=CloseCode.FORBIDDEN)
            return
        except Exception as erro:  # noqa: BLE001 — NACK em vez de conexão caída
            logger.exception("sync: falha ao persistir lote")
            await self.send_envelope(
                MessageType.NACK,
                {"failed": [{"event_id": e.get("event_id"), "error": str(erro)} for e in eventos]},
                correlation_id=envelope.get("message_id"),
            )
            return

        await database_sync_to_async(self._avancar_cursor)(maior)
        await self.send_envelope(
            MessageType.ACK,
            {
                "received": [str(e.get("event_id")) for e in eventos],
                "stored": len(aceitos),
                "cursor": maior,
            },
            correlation_id=envelope.get("message_id"),
        )
        await database_sync_to_async(self._enfileirar_aplicacao)([e.pk for e in aceitos])

    async def handle_ack(self, _envelope, payload):
        proprio = await database_sync_to_async(nodes.self_node)()
        # `self.node` é quem a conexão autenticou: um ACK só vale para o que
        # foi endereçado a ele.
        await database_sync_to_async(dispatch.apply_ack)(
            proprio, payload, target_node=self.node
        )

    async def handle_pull_request(self, envelope, _payload):
        """O nó local pediu o que houver para ele. Envia um lote e para."""
        proprio = await database_sync_to_async(nodes.self_node)()
        lote, _bytes = await database_sync_to_async(dispatch.collect_batch)(proprio, self.node)
        if not lote:
            await self.send_envelope(
                MessageType.SYNC_AVAILABLE, {"pending": 0},
                correlation_id=envelope.get("message_id"),
            )
            return

        corpo = await database_sync_to_async(dispatch.serialize_batch)(lote)
        await self.send_envelope(
            MessageType.EVENT_BATCH,
            {"events": corpo},
            correlation_id=envelope.get("message_id"),
            sequence_start=lote[0].sequence,
            sequence_end=lote[-1].sequence,
        )
        await database_sync_to_async(dispatch.mark_sent)(lote)

    # ── auxiliares síncronos ────────────────────────────────────────────────
    def _tocar_presenca(self):
        self.node.last_seen_at = timezone.now()
        self.node.save(update_fields=["last_seen_at", "updated_at"])

    def _avancar_cursor(self, sequencia):
        if sequencia > self.node.last_received_cursor:
            self.node.last_received_cursor = sequencia
            self.node.last_sync_at = timezone.now()
            self.node.save(update_fields=["last_received_cursor", "last_sync_at", "updated_at"])

    def _enfileirar_aplicacao(self, ids):
        """Pede a aplicação ao worker. Falhar aqui NÃO é perder nada.

        Os eventos já estão commitados na inbox quando esta função roda — o
        ACK só sai depois disso. Se o broker estiver fora do ar, enfileirar
        falha, mas `sync.apply_pending_events` roda no beat a cada 15s e
        encontra exatamente os mesmos eventos.

        Deixar a exceção subir derrubaria a conexão da loja por causa de um
        Redis reiniciando — com o dado seguro no banco o tempo todo.
        """
        if not ids:
            return
        from apps.synchronization.tasks.apply import apply_pending_events

        try:
            apply_pending_events.delay([str(i) for i in ids])
        except Exception:  # noqa: BLE001 — broker fora do ar é cenário previsto
            logger.warning(
                "sync: não foi possível enfileirar a aplicação de %s evento(s); "
                "o beat os aplica na próxima passada.", len(ids), exc_info=True,
            )

    def _token_do_scope(self):
        """Bearer do header do handshake. Nunca da query string (§8.2)."""
        cabecalhos = dict(self.scope.get("headers", []))
        bruto = cabecalhos.get(b"authorization", b"").decode().strip()
        return bruto[7:].strip() if bruto.lower().startswith("bearer ") else ""

    def _client_ip(self):
        cliente = self.scope.get("client") or []
        return cliente[0] if cliente else None
