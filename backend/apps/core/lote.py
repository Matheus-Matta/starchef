"""Criar muitos registros de uma vez, sem perder o que o `save()` dispararia.

`bulk_create` grava numa inserção só, mas pula o `post_save` — e é por ele que
nascem o evento de sincronização (loja ⇄ nuvem) e o aviso de tempo real. Uma
venda criava item, movimento de estoque e auditoria um a um, cada um com a
sua ida ao banco e a sua captura; com 50 itens, centenas de idas.

Aqui grava-se de uma vez e o `post_save(created=True)` de cada registro é
disparado à mão, então TODO receptor roda como num `save()` — sem lista de
receptores para manter em dia. Os caros já trabalham em lote dentro da venda
(`synchronization/services/outbox_lote.py`, `realtime/envio_em_lote.py`).

O que NÃO roda é o `save()` do modelo: quem o sobrescreve (ex. o id calculado
de `StockMovement`) precisa fazer o mesmo antes de chamar.
"""
from django.db import router
from django.db.models.signals import post_save
from django.utils import timezone


def criar_em_lote(modelo, objetos):
    """Insere `objetos` de uma vez e dispara o `post_save` de cada um."""
    objetos = list(objetos)
    if not objetos:
        return []
    banco = router.db_for_write(modelo)
    criados = modelo._base_manager.using(banco).bulk_create(objetos)
    for objeto in criados:
        post_save.send(sender=modelo, instance=objeto, created=True, update_fields=None,
                       raw=False, using=banco)
    return criados


def atualizar_em_lote(modelo, objetos, campos):
    """`save(update_fields=campos)` de cada um, numa gravação só.

    `bulk_update` não roda o `auto_now`: o `updated_at` (que a sincronização
    usa como versão) é posto aqui, igual para todos, quando está nos campos.
    """
    objetos, campos = list(objetos), list(campos)
    if not objetos:
        return []
    if "updated_at" in campos:
        agora = timezone.now()
        for objeto in objetos:
            objeto.updated_at = agora
    banco = router.db_for_write(modelo)
    modelo._base_manager.using(banco).bulk_update(objetos, campos)
    alterados = frozenset(campos)
    for objeto in objetos:
        post_save.send(sender=modelo, instance=objeto, created=False, update_fields=alterados,
                       raw=False, using=banco)
    return objetos
