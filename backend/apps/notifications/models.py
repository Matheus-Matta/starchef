from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TenantBaseModel


class Notification(TenantBaseModel):
    """Notificação destinada a um usuário, com escopo de conta (multi-tenant).

    Criada pelos serviços/sinais e entregue em tempo real via WebSocket. É
    persistida para permitir listagem histórica (últimas N + carregar mais).
    """

    LEVEL_INFO = "info"
    LEVEL_SUCCESS = "success"
    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "error"
    LEVEL_CHOICES = [
        (LEVEL_INFO, "Info"),
        (LEVEL_SUCCESS, "Success"),
        (LEVEL_WARNING, "Warning"),
        (LEVEL_ERROR, "Error"),
    ]

    CATEGORY_SYSTEM = "system"
    CATEGORY_ORDER = "order"
    CATEGORY_CASH = "cash"
    CATEGORY_PAYMENT = "payment"
    CATEGORY_KITCHEN = "kitchen"
    CATEGORY_STOCK = "stock"
    CATEGORY_CHOICES = [
        (CATEGORY_SYSTEM, "Sistema"),
        (CATEGORY_ORDER, "Pedidos"),
        (CATEGORY_CASH, "Caixa"),
        (CATEGORY_PAYMENT, "Pagamentos"),
        (CATEGORY_KITCHEN, "Cozinha"),
        (CATEGORY_STOCK, "Estoque"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="notifications",
        on_delete=models.CASCADE,
        db_index=True,
    )
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default=CATEGORY_SYSTEM, db_index=True)
    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    # Rota do frontend para onde a notificação leva (ex.: "/caixa", "/pedidos/<id>").
    url = models.CharField(max_length=300, blank=True)
    # Referência opcional ao objeto de origem (para deduplicação/rastreio).
    entity = models.CharField(max_length=120, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "created_at"]),
            models.Index(fields=["account", "recipient", "created_at"]),
            models.Index(fields=["entity", "object_id"]),
        ]

    def __str__(self):
        return f"{self.title} → {self.recipient_id}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])
