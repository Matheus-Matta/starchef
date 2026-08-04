from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.restaurants.models import Restaurant
from apps.restaurants.services import sync_branch_for_restaurant


@receiver(post_save, sender=Restaurant)
def on_restaurant_saved(sender, instance, **kwargs):
    """Mantém a Branch única do restaurante sincronizada em criar/editar/deletar.

    Soft-delete (`TenantBaseModel.delete()`) também passa por aqui — ele seta
    `deleted_at` e chama `save()` internamente, então este mesmo handler
    propaga o delete pra Branch sem precisar de um `post_delete` à parte.
    """
    sync_branch_for_restaurant(instance)
