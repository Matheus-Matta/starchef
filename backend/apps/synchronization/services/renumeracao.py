"""Número sequencial por pai que os dois lados deram ao mesmo tempo.

A rodada de cozinha é numerada por comanda (e por pedido) com `max + 1`. Com o
terminal alternando entre loja e nuvem, cada lado cria a SUA "rodada 2" da
mesma comanda, e o índice único (pai, número) recusava a segunda na chegada:
conflito, a rodada nunca aplicada, os itens dela esperando para sempre.

A regra é a MESMA nos dois lados, para os dois terminarem iguais sem conversar:
a linha de id MENOR fica com o número; a outra vai para o próximo livre. A
mudança ganha `updated_at` de agora e vira evento — é assim que o outro lado,
que pode ter decidido antes, recebe a versão mais nova e converge.
"""
import logging

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

logger = logging.getLogger(__name__)


def resolver(model, entrada, kwargs, event, inserir):
    """Resolve a colisão de número, se for esse o caso. Devolve True se resolveu."""
    if not entrada.renumber_on_collision:
        return False
    pai, campo = entrada.renumber_on_collision
    if kwargs.get(pai) is None or kwargs.get(campo) is None:
        return False
    gerente = model._base_manager
    local = gerente.filter(**{pai: kwargs[pai], campo: kwargs[campo]}).exclude(
        pk=event.entity_id
    ).first()
    if local is None:
        return False

    from apps.synchronization.services import outbox

    with transaction.atomic():
        proximo = (gerente.filter(**{pai: kwargs[pai]}).aggregate(m=Max(campo))["m"] or 0) + 1
        if str(event.entity_id) > str(local.pk):
            kwargs = {**kwargs, campo: proximo, "updated_at": timezone.now()}
            inserir(kwargs)
            cedeu = gerente.get(pk=event.entity_id)
        else:
            setattr(local, campo, proximo)
            local.save()
            inserir(kwargs)
            cedeu = local
        outbox.record(cedeu, force=True)
    logger.warning(
        "sync: %s %s foi para o número %s — o mesmo número nasceu nos dois lados",
        model.__name__, cedeu.pk, proximo,
    )
    return True


def resolver_atualizacao(model, entrada, existente, kwargs, atualizar):
    """O mesmo, quando a linha JÁ existe e a outra ponta mudou o número dela
    para um que outra linha daqui ocupa."""
    if not entrada.renumber_on_collision:
        return False
    pai, campo = entrada.renumber_on_collision
    if kwargs.get(pai) is None or kwargs.get(campo) is None:
        return False
    gerente = model._base_manager
    outra = gerente.filter(**{pai: kwargs[pai], campo: kwargs[campo]}).exclude(
        pk=existente.pk
    ).first()
    if outra is None:
        return False

    from apps.synchronization.services import outbox

    with transaction.atomic():
        proximo = (gerente.filter(**{pai: kwargs[pai]}).aggregate(m=Max(campo))["m"] or 0) + 1
        if str(existente.pk) > str(outra.pk):
            atualizar({**kwargs, campo: proximo, "updated_at": timezone.now()})
            cedeu = gerente.get(pk=existente.pk)
        else:
            setattr(outra, campo, proximo)
            outra.save()
            atualizar(kwargs)
            cedeu = outra
        outbox.record(cedeu, force=True)
    return True
