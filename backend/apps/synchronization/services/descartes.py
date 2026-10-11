"""Registra no histórico (`SyncDiscard`) o que chegou e foi ignorado.

Nunca derruba quem chamou: o registro é um extra, e a operação (um recebimento,
a aplicação de um evento) não pode falhar porque o histórico falhou. Um erro
aqui vira log, dentro de um savepoint para não envenenar a transação de fora.
"""
import json
import logging

from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, transaction

logger = logging.getLogger(__name__)


def registrar(*, origem, motivo, entity_type, entity_id, dados, account_id=None,
              versao_recebida=0, versao_local=0, event=None, usuario=None):
    from apps.synchronization.models import SyncDiscard

    try:
        with transaction.atomic():
            return SyncDiscard.objects.create(
                origem=origem, motivo=motivo, entity_type=entity_type,
                entity_id=str(entity_id), dados=_json(dados), account_id=account_id,
                versao_recebida=int(versao_recebida or 0), versao_local=int(versao_local or 0),
                event=event, usuario=usuario if getattr(usuario, "pk", None) else None,
            )
    except DatabaseError:
        logger.exception("sync: não registrou o descarte de %s/%s", entity_type, entity_id)
        return None


def do_evento(event, motivo, *, versao_local=0, dados=None):
    """O descarte de um evento de sincronização, com o que ele trazia."""
    from apps.synchronization.models import SyncDiscard

    payload = event.payload or {}
    return registrar(
        origem=SyncDiscard.ORIGEM_SYNC, motivo=motivo, entity_type=event.entity_type,
        entity_id=event.entity_id, dados=payload.get("fields", {}) if dados is None else dados,
        account_id=event.account_id,
        versao_recebida=payload.get("entity_version") or event.entity_version,
        versao_local=versao_local, event=event,
    )


def _json(dados):
    """UUID, Decimal e data viram texto — o que chegou, legível e recuperável."""
    return json.loads(json.dumps(dados or {}, cls=DjangoJSONEncoder, default=str))
