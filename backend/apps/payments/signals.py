from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.payments.defaults import ensure_default_payment_methods
from apps.restaurants.models import Restaurant
from apps.synchronization.services.outbox_eco import is_applying


@receiver(post_save, sender=Restaurant, dispatch_uid="payments_seed_defaults")
def seed_payment_methods_for_restaurant(sender, instance, created, **kwargs):
    # Restaurante que CHEGA pela sincronização não ganha formas locais: as da
    # origem chegam sozinhas, com o UUID de lá. Criadas aqui, dentro do apply,
    # nenhuma virava evento — ficavam só na loja, e um recebimento com uma
    # delas nunca seria aplicado na nuvem
    # (test_restaurante_aplicado_nao_cria_formas_de_pagamento_locais).
    if created and not is_applying():
        ensure_default_payment_methods(restaurant=instance)
