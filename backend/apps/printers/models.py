from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Printer(TenantModel):
    CONNECTION_WINDOWS = "windows"
    CONNECTION_NETWORK = "network"
    CONNECTION_SERIAL = "serial"

    CONNECTION_CHOICES = [
        (CONNECTION_WINDOWS, "Windows / USB"),
        (CONNECTION_NETWORK, "TCP/IP"),
        (CONNECTION_SERIAL, "Serial"),
    ]

    DRIVER_BROWSER = "browser"
    DRIVER_ESCPOS = "escpos"

    DRIVER_CHOICES = [
        (DRIVER_BROWSER, "Browser"),
        (DRIVER_ESCPOS, "ESC/POS"),
    ]

    name = models.CharField(max_length=120)
    # Setor cadastrado (TableSector) — mesmos setores usados nas mesas/produtos.
    sector = models.ForeignKey(
        "restaurants.TableSector",
        null=True,
        blank=True,
        related_name="printers",
        on_delete=models.SET_NULL,
    )
    driver_type = models.CharField(max_length=24, choices=DRIVER_CHOICES, default=DRIVER_BROWSER)
    connection_type = models.CharField(
        max_length=16,
        choices=CONNECTION_CHOICES,
        default=CONNECTION_WINDOWS,
    )
    endpoint = models.CharField(max_length=255, blank=True)
    host = models.GenericIPAddressField(null=True, blank=True)
    port = models.PositiveIntegerField(default=9100)
    timeout_seconds = models.PositiveIntegerField(default=10)
    auto_print = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_printer_by_branch"),
        ]

    def __str__(self):
        return self.name


class Scale(TenantModel):
    """Balanca do caixa/PDV. O agente local le a porta serial/USB e envia leituras para a API."""

    PROTOCOL_GENERIC = "generic"
    PROTOCOL_TOLEDO_PRT2 = "toledo_prt2"
    PROTOCOL_FILIZOLA = "filizola"
    PROTOCOL_URANO = "urano"

    PROTOCOL_CHOICES = [
        (PROTOCOL_GENERIC, "Generico"),
        (PROTOCOL_TOLEDO_PRT2, "Toledo PRT2"),
        (PROTOCOL_FILIZOLA, "Filizola"),
        (PROTOCOL_URANO, "Urano"),
    ]

    name = models.CharField(max_length=120)
    # Setor cadastrado (TableSector) — mesmos setores usados nas mesas/produtos.
    sector = models.ForeignKey(
        "restaurants.TableSector",
        null=True,
        blank=True,
        related_name="scales",
        on_delete=models.SET_NULL,
    )
    protocol = models.CharField(max_length=24, choices=PROTOCOL_CHOICES, default=PROTOCOL_GENERIC)
    port = models.CharField(max_length=64, blank=True, help_text="Porta usada pelo agente local, ex.: COM3 ou /dev/ttyUSB0.")
    reading_max_age_seconds = models.PositiveIntegerField(
        default=120,
        help_text="Idade maxima de uma leitura para ser aceita em um pedido.",
    )

    # Produto "por kilo" que define o preco/kg da nota gerada nesta balanca.
    product = models.ForeignKey(
        "menu.Product",
        null=True,
        blank=True,
        related_name="scales",
        on_delete=models.SET_NULL,
        help_text="Produto por kilo usado para precificar a pesagem.",
    )
    # Impressora que recebe a nota de pesagem (o agente local faz o polling dela).
    printer = models.ForeignKey(
        Printer,
        null=True,
        blank=True,
        related_name="scales",
        on_delete=models.SET_NULL,
        help_text="Impressora onde a nota de pesagem sera impressa.",
    )
    # Pedido/comanda ao qual as pesagens desta balanca sao lancadas (fluxo automatico).
    active_order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        related_name="bound_scales",
        on_delete=models.SET_NULL,
        help_text="Pedido corrente vinculado a balanca (usado no gatilho automatico).",
    )
    # Ao receber uma leitura estavel, lanca o item e gera a nota automaticamente.
    auto_print = models.BooleanField(default=False)
    auto_print_delay_seconds = models.PositiveIntegerField(
        default=3,
        help_text="Segundos que a balanca deve ficar estavel antes de imprimir (aplicado pelo agente).",
    )
    agent_instance_id = models.CharField(
        max_length=120,
        blank=True,
        help_text="Identificador do PDV Desktop que possui a leitura exclusiva da balanca.",
    )
    agent_lease_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Validade da posse exclusiva da balanca pelo agente local.",
    )
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_scale_by_branch"),
        ]

    def __str__(self):
        return self.name


class ScaleReading(TenantModel):
    """Leitura de peso enviada pelo agente local (ou digitada manualmente no PDV)."""

    SOURCE_AGENT = "agent"
    SOURCE_MANUAL = "manual"

    SOURCE_CHOICES = [
        (SOURCE_AGENT, "Agente local"),
        (SOURCE_MANUAL, "Digitacao manual"),
    ]

    scale = models.ForeignKey(Scale, null=True, blank=True, related_name="readings", on_delete=models.SET_NULL)
    weight_kg = models.DecimalField(max_digits=9, decimal_places=3)
    tare_kg = models.DecimalField(max_digits=9, decimal_places=3, default=0)
    is_stable = models.BooleanField(default=True)
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default=SOURCE_AGENT)
    order_item = models.ForeignKey(
        "orders.OrderItem",
        null=True,
        blank=True,
        related_name="scale_readings",
        on_delete=models.SET_NULL,
        help_text="Preenchido quando a leitura vira um item de pedido.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["scale", "created_at"]),
        ]

    @property
    def net_weight_kg(self):
        return self.weight_kg - self.tare_kg

    def __str__(self):
        return f"{self.weight_kg} kg ({self.get_source_display()})"


class PrintJob(TenantModel):
    TYPE_KITCHEN = "kitchen_ticket"
    TYPE_BAR = "bar_ticket"
    TYPE_TABLE_BILL = "table_bill"
    TYPE_RECEIPT = "receipt"
    TYPE_PAYMENT = "payment_receipt"
    TYPE_CASH_CLOSE = "cash_close"
    TYPE_WEIGH = "weigh_ticket"  # nota de pesagem (balanca por kilo)
    TYPE_FISCAL = "fiscal_danfe"  # cupom fiscal DANFE NFC-e

    STATUS_PENDING = "pending"
    STATUS_RENDERED = "rendered"
    STATUS_PRINTED = "printed"
    STATUS_FAILED = "failed"

    printer = models.ForeignKey(Printer, null=True, blank=True, related_name="jobs", on_delete=models.SET_NULL)
    order = models.ForeignKey("orders.Order", null=True, blank=True, related_name="print_jobs", on_delete=models.SET_NULL)
    job_type = models.CharField(max_length=32, default=TYPE_RECEIPT, db_index=True)
    status = models.CharField(max_length=24, default=STATUS_RENDERED, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    html_content = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    printed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="print_jobs",
        on_delete=models.SET_NULL,
    )
    printed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["branch", "job_type", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.job_type} - {self.status}"

