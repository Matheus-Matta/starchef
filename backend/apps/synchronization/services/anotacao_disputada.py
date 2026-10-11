"""A mesma anotação de comanda cobrada nos dois lados: o mais novo fica com ela.

No restaurante todo mundo usa a loja ou todo mundo usa a nuvem; os dois só
recebem ao mesmo tempo na TROCA (a loja cai, volta). Nessa janela, dois caixas
podem fechar a mesma comanda, um em cada lado. Nada é bloqueado — o caixa
decide —, mas a chegada do item da outra ponta não pode travar a fila: ela
batia em `unique_order_item_per_command_item` e o estoque do item ficava
retentando para sempre.

A regra é a mesma nos dois lados, para terminarem iguais sem conversar: o item
de `updated_at` MAIS NOVO fica com a anotação; o mais velho entra (ou fica)
assim mesmo — o pedido dele foi pago com ele —, só que sem o vínculo. Quem
perdeu o vínculo AQUI vira evento, para o outro lado convergir.
"""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)

CAMPO = "command_item_id"


def resolver(model, kwargs, event, gravar):
    """Resolve a disputa pela anotação, se for esse o caso. True se resolveu.

    Vale para a INSERÇÃO e para a ATUALIZAÇÃO: o item que entrou sem o vínculo
    pode, depois, mudar do outro lado (a cozinha marca pronto) e chegar com o
    vínculo de volta, mais novo que o daqui.
    """
    if model.__name__ != "OrderItem" or not kwargs.get(CAMPO):
        return False
    local = (
        model._base_manager.filter(**{CAMPO: kwargs[CAMPO]})
        .exclude(pk=event.entity_id)
        .first()
    )
    if local is None:
        return False

    from apps.synchronization.services import outbox, serialization

    versao_local = serialization.entity_version(local)
    remoto_mais_novo = int(event.entity_version or 0) > versao_local
    _guardar_quem_perdeu(event, local, kwargs, remoto_mais_novo, versao_local)
    with transaction.atomic():
        if remoto_mais_novo:
            local.command_item = None
            local.save()
            outbox.record(local, force=True)
            gravar(kwargs)
        else:
            gravar({**kwargs, CAMPO: None})
    logger.warning(
        "sync: anotação %s cobrada nos dois lados — ficou com o item %s; o item %s "
        "ficou sem o vínculo",
        kwargs[CAMPO],
        event.entity_id if remoto_mais_novo else local.pk,
        local.pk if remoto_mais_novo else event.entity_id,
    )
    return True


def _guardar_quem_perdeu(event, local, kwargs, remoto_mais_novo, versao_local):
    """O vínculo que sai vai ao histórico, com o item como estava."""
    from apps.synchronization.models import SyncDiscard
    from apps.synchronization.services import descartes, serialization

    if remoto_mais_novo:
        dados = serialization.build_payload(local, _entrada(), origin_node_id=None)["fields"]
        entity_id = local.pk
    else:
        dados, entity_id = (event.payload or {}).get("fields", {}), event.entity_id
    descartes.registrar(
        origem=SyncDiscard.ORIGEM_SYNC, motivo=SyncDiscard.MOTIVO_ANOTACAO_PERDEU_VINCULO,
        entity_type="order_item", entity_id=entity_id, dados=dados,
        account_id=event.account_id, versao_recebida=event.entity_version,
        versao_local=versao_local, event=event,
    )


def _entrada():
    from apps.synchronization.services.registry import registry

    return registry.require("order_item")
