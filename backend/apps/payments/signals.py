from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.payments.defaults import ensure_default_payment_methods
from apps.restaurants.models import Restaurant


@receiver(post_save, sender=Restaurant, dispatch_uid="payments_seed_defaults")
def seed_payment_methods_for_restaurant(sender, instance, created, **kwargs):
    if created:
        ensure_default_payment_methods(restaurant=instance)
