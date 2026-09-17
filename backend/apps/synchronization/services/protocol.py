"""O envelope v1: como uma mensagem é montada, lida e conferida.

Regra que atravessa o arquivo inteiro: `account_id` viaja no envelope só para
rastreabilidade. Quem autoriza é a conexão autenticada, nunca o campo.
"""
import uuid
from datetime import datetime, timezone as dt_timezone

from apps.synchronization.constants import PROTOCOL_VERSION, MessageType
from apps.synchronization.services import crypto

#: Campos que identificam a mensagem e entram como dados autenticados do AES-GCM.
HEADER_FIELDS = (
    "protocol_version",
    "message_id",
    "correlation_id",
    "source_node_id",
    "target_node_id",
    "account_id",
    "message_type",
    "sequence_start",
    "sequence_end",
    "sent_at",
    "key_id",
)


class ProtocolError(ValueError):
    """Envelope malformado, incompatível ou com checksum divergente."""


def _now_iso():
    return datetime.now(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def associated_data(envelope):
    """Bytes autenticados (não cifrados) do AES-GCM.

    Mexer em qualquer campo do cabeçalho — trocar o `target_node_id` para o de
    outra conta, por exemplo — invalida a tag e a mensagem nem é decifrada.
    """
    cabecalho = {campo: envelope.get(campo) for campo in HEADER_FIELDS}
    return crypto.canonical_json(cabecalho).encode("utf-8")


def build(message_type, *, source_node_id, target_node_id, account_id, payload,
          key=None, key_id="", correlation_id=None, sequence_start=None,
          sequence_end=None, message_id=None):
    """Monta o envelope. Com `key`, o payload vai cifrado; sem, vai em claro.

    Sem chave o transporte continua obrigatoriamente WSS — o AES-GCM é uma
    camada ADICIONAL, e o modo em claro existe para depuração local.
    """
    if message_type not in MessageType.ALL:
        raise ProtocolError(f"Tipo de mensagem desconhecido: {message_type}")

    envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "message_id": str(message_id or uuid.uuid4()),
        "correlation_id": str(correlation_id) if correlation_id else None,
        "source_node_id": str(source_node_id) if source_node_id else None,
        "target_node_id": str(target_node_id) if target_node_id else None,
        "account_id": str(account_id) if account_id else None,
        "message_type": message_type,
        "sequence_start": sequence_start,
        "sequence_end": sequence_end,
        "sent_at": _now_iso(),
        "key_id": key_id or "",
    }
    envelope["checksum"] = crypto.checksum(payload)
    if key:
        nonce, ciphertext = crypto.encrypt(payload, key, associated_data(envelope))
        envelope["nonce"] = nonce
        envelope["ciphertext"] = ciphertext
    else:
        envelope["nonce"] = None
        envelope["payload"] = payload
    return envelope


def parse(envelope, key=None):
    """Valida versão e checksum e devolve o payload já decifrado.

    A ordem importa e é a do plano: versão, forma, decifragem, checksum. Só
    depois de tudo isso o destino pode responder RECEIVED.
    """
    if not isinstance(envelope, dict):
        raise ProtocolError("Envelope não é um objeto JSON.")

    versao = envelope.get("protocol_version")
    if versao != PROTOCOL_VERSION:
        raise ProtocolError(f"Versão de protocolo incompatível: {versao} (esperado {PROTOCOL_VERSION})")

    tipo = envelope.get("message_type")
    if tipo not in MessageType.ALL:
        # Evento desconhecido não derruba a conexão (§17): quem chama decide.
        raise ProtocolError(f"Tipo de mensagem desconhecido: {tipo}")

    if envelope.get("ciphertext"):
        if not key:
            raise ProtocolError("Mensagem cifrada recebida sem chave configurada.")
        try:
            payload = crypto.decrypt(
                envelope.get("nonce"), envelope["ciphertext"], key, associated_data(envelope)
            )
        except Exception as erro:  # noqa: BLE001 — qualquer falha aqui é a mesma coisa
            raise ProtocolError(f"Falha ao decifrar o payload: {erro}") from erro
    else:
        payload = envelope.get("payload")

    esperado = envelope.get("checksum")
    if esperado and crypto.checksum(payload) != esperado:
        raise ProtocolError("Checksum divergente: o conteúdo não é o que a origem enviou.")

    return payload


def error_envelope(reason, *, code="protocol_error", correlation_id=None, detail=None):
    """Resposta de erro. Nunca leva payload — só o motivo."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_id": str(uuid.uuid4()),
        "correlation_id": str(correlation_id) if correlation_id else None,
        "message_type": MessageType.ERROR,
        "sent_at": _now_iso(),
        "payload": {"code": code, "reason": reason, "detail": detail or ""},
    }
