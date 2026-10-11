"""A pesagem na comanda identificada pelo UUID que o aparelho deu a ela.

A balança manda o peso no segundo em que a loja reinicia: a loja grava e cai
antes de responder, o terminal manda à nuvem — e a comanda ficava com o prato
duas vezes. Com o UUID do aparelho, tudo o que a pesagem cria tem id CALCULADO
dele: a leitura (o próprio UUID), a anotação, os adicionais e a rodada de
produção. O reenvio, no mesmo servidor ou no outro, é a MESMA pesagem; a
sincronização junta as cópias pelo id.
"""
import uuid

_ESPACO = uuid.UUID("8c3e5a17-2b9d-4f61-a0c4-7d1e9b3f5a62")


def id_da_anotacao(pesagem_id):
    return uuid.uuid5(_ESPACO, f"pesagem:{pesagem_id}")


def id_do_adicional(pesagem_id, posicao):
    return uuid.uuid5(_ESPACO, f"pesagem:{pesagem_id}:adicional:{posicao}")


def serial_do_lote(pesagem_id):
    return uuid.uuid5(_ESPACO, f"pesagem:{pesagem_id}:lote")


def ja_pesada(scale, pesagem_id):
    """A leitura desta pesagem, se ela JÁ foi lançada na comanda (reenvio)."""
    if pesagem_id is None:
        return None
    from apps.printers.models import ScaleReading

    return (
        ScaleReading.all_objects.select_related("command_item")
        .filter(pk=pesagem_id, account_id=scale.account_id)
        .exclude(command_item=None)
        .first()
    )


def guardar_reenvio(leitura, user, dados):
    """O reenvio é ignorado (a pesagem já existe), mas fica no histórico."""
    from apps.synchronization.models import SyncDiscard
    from apps.synchronization.services import descartes

    descartes.registrar(
        origem=SyncDiscard.ORIGEM_API, motivo=SyncDiscard.MOTIVO_REENVIO,
        entity_type="scale_reading", entity_id=leitura.pk, account_id=leitura.account_id,
        dados=dict(dados), usuario=user,
    )
