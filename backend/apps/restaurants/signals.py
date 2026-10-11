from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.restaurants.models import Restaurant
from apps.restaurants.services import sync_branch_for_restaurant
from apps.synchronization.services.outbox_eco import is_applying


@receiver(post_save, sender=Restaurant)
def on_restaurant_saved(sender, instance, **kwargs):
    """Mantém a Branch única do restaurante sincronizada em criar/editar/deletar.

    Soft-delete (`TenantBaseModel.delete()`) também passa por aqui — ele seta
    `deleted_at` e chama `save()` internamente, então este mesmo handler
    propaga o delete pra Branch sem precisar de um `post_delete` à parte.

    Restaurante que CHEGA pela sincronização não deriva filial: a filial já foi
    derivada no nó de origem e chega por conta própria, com o UUID de lá.
    Derivar aqui criava uma segunda filial com UUID local, e a próxima edição
    do restaurante batia em `unique_branch_name_by_restaurant` — evento falhando
    para sempre (test_restaurante_chegado_nao_deriva_filial).
    """
    if is_applying():
        return
    sync_branch_for_restaurant(instance)
