from django.db import models

from apps.core.models import TenantBaseModel


class ServiceLevelAgreement(TenantBaseModel):
    """SLA operacional, separado da Estação KDS (Sprint 6 · STC-065/066).

    Um SLA define um tempo-alvo e um limite de alerta por tipo de operação e pode
    ser vinculado a vários restaurantes (M2M). O KDS usa o SLA aplicável para
    calcular alertas de tempo.
    """

    TYPE_SERVICE = "service"    # atendimento
    TYPE_PREP = "prep"          # preparo
    TYPE_DELIVERY = "delivery"  # entrega
    TYPE_PICKUP = "pickup"      # retirada
    TYPE_OTHER = "other"

    TYPE_CHOICES = [
        (TYPE_SERVICE, "Atendimento"),
        (TYPE_PREP, "Preparo"),
        (TYPE_DELIVERY, "Entrega"),
        (TYPE_PICKUP, "Retirada"),
        (TYPE_OTHER, "Outro"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Baixa"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "Alta"),
        (PRIORITY_URGENT, "Urgente"),
    ]

    name = models.CharField(max_length=120)
    sla_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PREP, db_index=True)
    target_minutes = models.PositiveIntegerField(default=15)
    alert_minutes = models.PositiveIntegerField(default=10, help_text="Minutos até disparar o alerta (deve ser ≤ tempo-alvo).")
    priority = models.CharField(max_length=12, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    is_active = models.BooleanField(default=True, db_index=True)
    restaurants = models.ManyToManyField("restaurants.Restaurant", blank=True, related_name="slas")
    # Um SLA é REUTILIZÁVEL: pode ser aplicado a vários quadros (estações) e/ou a
    # várias colunas específicas. O KDS resolve o tempo-alvo de um card assim:
    # coluna do card em `columns` → senão estação do card em `stations` → senão
    # o sla_minutes da estação → senão o padrão do app.
    stations = models.ManyToManyField("kitchen.KdsStation", blank=True, related_name="slas")
    columns = models.ManyToManyField("kitchen.KdsColumn", blank=True, related_name="slas")

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["account", "sla_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_sla_type_display()})"
