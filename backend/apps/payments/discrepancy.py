"""Divergência de vendas: dinheiro que entrou sem venda registrada no PDV.

Num pico, pedidos passam sem lançamento: o caixa recebe (PIX, cartão,
dinheiro), mas não existe pedido — e, portanto, nenhuma NFC-e. A tentação é
criar um "pedido fictício" com o valor que falta e emitir a nota. Isso mistura
conciliação financeira com documento fiscal: a NFC-e de um pedido que não
existiu, emitida depois, não regulariza a mercadoria que já circulou sem nota
(a SEFAZ-RJ aponta a denúncia espontânea para esse caso).

Por isso a divergência é um registro ADMINISTRATIVO, separado de pedido, venda
e nota: guarda quanto, em que formas de pagamento, em qual sessão de caixa e
por quê. A regularização fiscal fica com o contador, e o sistema só registra o
desfecho (`regularization_note`).
"""
from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class SalesDiscrepancy(TenantModel):
    STATUS_OPEN = "open"
    STATUS_REVIEWED = "reviewed"
    STATUS_REGULARIZED = "regularized"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Aberta"),
        (STATUS_REVIEWED, "Analisada"),
        (STATUS_REGULARIZED, "Regularizada"),
        (STATUS_CANCELLED, "Cancelada"),
    ]
    #: Estados que ainda contam como dinheiro sem venda registrada.
    COUNTED_STATUSES = (STATUS_OPEN, STATUS_REVIEWED, STATUS_REGULARIZED)

    cash_register = models.ForeignKey(
        "payments.CashRegister", related_name="sales_discrepancies", on_delete=models.PROTECT
    )
    # A SOMA das formas, calculada no servidor — nunca informada pelo cliente.
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # [{"payment_method": id, "name": "PIX", "method_type": "pix", "amount": "2000.00"}]
    # O nome e o tipo são um retrato: renomear a forma depois não pode
    # reescrever o que o gerente registrou naquele fechamento.
    by_payment_method = models.JSONField(default=list)
    reason = models.TextField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name="sales_discrepancies_reviewed", on_delete=models.SET_NULL,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    regularized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name="sales_discrepancies_regularized", on_delete=models.SET_NULL,
    )
    regularized_at = models.DateTimeField(null=True, blank=True)
    # O desfecho fiscal, nas palavras de quem regularizou (ex.: "Denúncia
    # espontânea protocolo 123, orientada pelo contador").
    regularization_note = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name="sales_discrepancies_cancelled", on_delete=models.SET_NULL,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["cash_register", "status"])]

    def __str__(self):
        return f"Divergência {self.amount} - {self.cash_register_id}"
