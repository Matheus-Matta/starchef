"""A fila da comanda automática (regras em `fila_da_comanda.py`)."""
from django.db import models
from django.utils import timezone


class FilaDaComanda(models.Model):
    """O último número lançado pela comanda automática, por restaurante.

    É também a TRAVA da fila: travar esta linha é o que põe as balanças em
    ordem. Não sincroniza (ver `synchronization/decisions.py`): cada servidor
    escolhe a partir do próprio cursor, e a conferência de "livre" é o que
    impede a repetição, não o cursor.
    """

    restaurant = models.OneToOneField(
        "restaurants.Restaurant", primary_key=True, on_delete=models.CASCADE,
        related_name="fila_da_comanda",
    )
    ultimo_numero = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "printers"
