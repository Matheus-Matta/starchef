"""Quando o destino já criou sozinho a linha que a origem está mandando.

O caso concreto que forçou este módulo: aplicar um `restaurant` vindo da nuvem
dispara, na loja, o `post_save` que cria a Branch espelho daquele restaurante —
com um UUID gerado ali. Logo em seguida chega o evento `branch` da nuvem, com o
MESMO (restaurante, nome) e um UUID diferente. O banco recusa:

    UNIQUE constraint failed: restaurants_branch.restaurant_id, ..._branch.name

E recusa para sempre: o evento tenta, falha, volta para a fila, tenta de novo,
até morrer. Os dois lados ficam permanentemente divergentes numa tabela que
ninguém tocou — só porque o destino é esperto demais.

A saída é a **adoção**: a linha local que nasceu de um efeito colateral e nunca
foi tocada pela sincronização cede o lugar para a identidade da origem. Duas
travas impedem que isso vire perda de dado:

1. só adota quem **nasceu aqui** — nenhum evento de sincronização já aplicado
   aponta para aquela linha;
2. só adota quando **a origem é a autoridade** daquela entidade pela política
   do catálogo. Um pedido nascido na loja jamais é adotado pela nuvem.

Fora dessas duas condições, o caso vira SyncConflict e espera decisão humana —
que é o comportamento certo para uma divergência que ninguém previu.
"""
import logging

from apps.synchronization.constants import ConflictResolution, Direction, EventStatus, NodeType
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)


def unique_field_sets(model):
    """Todos os conjuntos de campos que o banco exige únicos, deste model."""
    conjuntos = []
    for campo in model._meta.concrete_fields:
        if campo.unique and not campo.primary_key:
            conjuntos.append((campo.attname,))
    for juntos in model._meta.unique_together:
        conjuntos.append(tuple(_attname(model, nome) for nome in juntos))
    for restricao in model._meta.constraints:
        campos = getattr(restricao, "fields", None)
        if campos:
            conjuntos.append(tuple(_attname(model, nome) for nome in campos))
    return conjuntos


def _attname(model, nome):
    """`restaurant` -> `restaurant_id` quando o campo é relação."""
    try:
        campo = model._meta.get_field(nome)
    except Exception:  # noqa: BLE001 — nome de constraint pode não ser campo
        return nome
    return campo.attname if campo.is_relation else campo.name


def find_local_duplicate(model, kwargs, remote_pk):
    """A linha local que ocupa a mesma chave única do registro que chegou."""
    gerente = getattr(model, "all_objects", model._default_manager)
    for campos in unique_field_sets(model):
        filtro = {campo: kwargs[campo] for campo in campos if campo in kwargs}
        if len(filtro) != len(campos) or not filtro:
            continue
        if any(valor is None for valor in filtro.values()):
            continue  # NULL não colide em índice único
        existente = gerente.filter(**filtro).exclude(pk=remote_pk).first()
        if existente is not None:
            return existente, campos
    return None, ()


def born_locally(model, instance):
    """A linha nunca foi alvo de um evento de sincronização aplicado aqui?

    Se já foi, ela tem identidade própria vinda do outro lado e apagá-la seria
    destruir um registro sincronizado — exatamente o que não pode acontecer.
    """
    from apps.synchronization.models import SyncEvent

    entrada = registry.for_model(model)
    if entrada is None:
        return False
    return not SyncEvent.objects.filter(
        direction=Direction.INBOUND,
        entity_type=entrada.entity_type,
        entity_id=str(instance.pk),
        status__in=[EventStatus.APPLIED, EventStatus.ACKNOWLEDGED],
    ).exists()


def origin_is_authority(entity_type, receiving_node_type):
    """A origem manda nesta entidade, neste sentido?"""
    entrada = registry.get(entity_type)
    if entrada is None:
        return False
    politica = entrada.conflict_policy
    if politica == ConflictResolution.CLOUD_WINS:
        # A nuvem manda: a loja adota o que vem de cima.
        return receiving_node_type == NodeType.LOCAL
    if politica == ConflictResolution.LOCAL_WINS:
        return receiving_node_type == NodeType.CLOUD
    # LAST_VERSION e MANUAL nunca adotam em silêncio.
    return False


def try_adopt(model, kwargs, event):
    """Tenta ceder o lugar da linha local. Devolve `(adotou, motivo)`."""
    duplicada, campos = find_local_duplicate(model, kwargs, event.entity_id)
    if duplicada is None:
        # Não é colisão de identidade: é outra regra do schema (campo
        # obrigatório ausente, FK inválida). Dizer isso no log evita meia hora
        # procurando uma duplicata que nunca existiu.
        return False, "não há duplicata local; a violação é de outra regra do schema"

    chave = ", ".join(campos)
    if not origin_is_authority(event.entity_type, event.target_node.node_type):
        return False, f"origem não é autoridade sobre {event.entity_type} ({chave})"

    if not born_locally(model, duplicada):
        return False, f"a linha local {duplicada.pk} já veio da sincronização ({chave})"

    # Apaga de verdade, não soft delete: a linha vai ser substituída pela
    # identidade da origem, e uma `deleted_at` deixaria o índice único ocupado.
    model._base_manager.filter(pk=duplicada.pk).delete()
    logger.info(
        "sync: adoção — linha local %s de %s cedeu lugar a %s (chave: %s)",
        duplicada.pk, model.__name__, event.entity_id, chave,
    )
    return True, f"linha local {duplicada.pk} adotada pela origem ({chave})"
