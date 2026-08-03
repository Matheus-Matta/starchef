from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.menu.models import Product


@receiver(post_save, sender=Product)
def ensure_primary_restaurant_is_available(sender, instance, created, raw=False, **kwargs):
    """Mantém compatibilidade com seeds e integrações que criam Product via ORM."""
    if created and not raw and instance.restaurant_id:
        instance.restaurants.add(instance.restaurant_id)
