"""Backfill: garante a Branch única (espelhada) de cada Restaurant já existente.

Daqui pra frente o signal `apps.restaurants.signals.on_restaurant_saved` cuida
disso sozinho a cada criar/editar/deletar restaurante — este comando só é
necessário uma vez, pra sincronizar restaurantes que já existiam antes dessa
mudança (idempotente, pode rodar de novo sem problema).

    python manage.py sync_restaurant_branches
"""
from django.core.management.base import BaseCommand

from apps.restaurants.models import Restaurant
from apps.restaurants.services import sync_branch_for_restaurant


class Command(BaseCommand):
    help = "Garante uma Branch (filial) por Restaurant existente, espelhando os campos do restaurante."

    def handle(self, *args, **options):
        count = 0
        for restaurant in Restaurant.all_objects.all():
            sync_branch_for_restaurant(restaurant)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"{count} restaurante(s) sincronizados com sua filial."))
