"""Excluir um produto/insumo solta os vínculos da NF-e de entrada.

O sinal fica deste lado de propósito: o cardápio não precisa saber que existe
nota de entrada. Ver `services.unlink.liberar_vinculos_de_apagado`.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.menu.models import Ingredient, Product


def _foi_excluido(instance, update_fields):
    if instance.deleted_at is None:
        return False
    # A exclusão lógica grava só `deleted_at`. Um save completo de algo já
    # excluído (sincronização, admin) também solta — repetir é inofensivo.
    return update_fields is None or "deleted_at" in update_fields


@receiver(post_save, sender=Ingredient, dispatch_uid="inbound_nfe_solta_insumo_excluido")
def soltar_insumo_excluido(sender, instance, update_fields=None, **kwargs):
    if _foi_excluido(instance, update_fields):
        from apps.inbound_nfe.services.unlink import liberar_vinculos_de_apagado

        liberar_vinculos_de_apagado(ingredient=instance)


@receiver(post_save, sender=Product, dispatch_uid="inbound_nfe_solta_produto_excluido")
def soltar_produto_excluido(sender, instance, update_fields=None, **kwargs):
    if _foi_excluido(instance, update_fields):
        from apps.inbound_nfe.services.unlink import liberar_vinculos_de_apagado

        liberar_vinculos_de_apagado(product=instance)
