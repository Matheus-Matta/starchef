import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class StockLocation(TenantModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_stock_location_by_branch"),
        ]

    def __str__(self):
        return self.name


class StockSettings(TenantModel):
    """Configuracao do estoque de uma filial.

    Uma por filial: FIFO/FEFO, obrigatoriedade de validade, bloqueio de vencido
    e de saldo negativo sao decisoes da operacao daquela unidade, nao da conta.
    """

    PICKING_FIFO = "fifo"
    PICKING_FEFO = "fefo"
    PICKING_CHOICES = [
        (PICKING_FIFO, "FIFO — primeiro a entrar, primeiro a sair"),
        (PICKING_FEFO, "FEFO — primeiro a vencer, primeiro a sair"),
    ]

    default_location = models.ForeignKey(
        StockLocation, null=True, blank=True, related_name="default_for_settings", on_delete=models.SET_NULL
    )
    picking_strategy = models.CharField(max_length=8, choices=PICKING_CHOICES, default=PICKING_FEFO)
    expiry_control_enabled = models.BooleanField(default=False)
    expiry_warning_days = models.PositiveSmallIntegerField(default=7)
    block_expired_stock = models.BooleanField(default=True)
    allow_negative_stock = models.BooleanField(default=False)
    require_label_scan_on_manual_exit = models.BooleanField(default=False)
    default_label_template = models.ForeignKey(
        "stock.StockLabelTemplate", null=True, blank=True, related_name="default_for_settings", on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = "configuracao de estoque"
        verbose_name_plural = "configuracoes de estoque"
        constraints = [
            models.UniqueConstraint(fields=["branch"], name="unique_stock_settings_by_branch"),
        ]

    def __str__(self):
        return f"Estoque - {self.branch or self.restaurant}"


class StockLabelTemplate(TenantModel):
    """Modelo de etiqueta impressa pelo navegador.

    As medidas sao em milimetros porque e assim que o papel adesivo e vendido,
    e a impressao usa `@page` do CSS — o navegador respeita mm melhor do que
    qualquer conversao para pixel feita aqui.
    """

    CODE_QR = "qr"
    CODE_BARCODE = "code128"
    CODE_CHOICES = [(CODE_QR, "QR Code"), (CODE_BARCODE, "Codigo de barras (Code 128)")]

    name = models.CharField(max_length=120)
    width_mm = models.DecimalField(max_digits=6, decimal_places=1, default=60)
    height_mm = models.DecimalField(max_digits=6, decimal_places=1, default=40)
    margin_mm = models.DecimalField(max_digits=5, decimal_places=1, default=2)
    columns = models.PositiveSmallIntegerField(default=1)
    code_type = models.CharField(max_length=12, choices=CODE_CHOICES, default=CODE_QR)
    font_size_pt = models.DecimalField(max_digits=4, decimal_places=1, default=8)
    show_ingredient = models.BooleanField(default=True)
    show_lot_code = models.BooleanField(default=True)
    show_supplier_lot = models.BooleanField(default=True)
    show_entered_at = models.BooleanField(default=True)
    show_expires_at = models.BooleanField(default=True)
    show_quantity = models.BooleanField(default=True)
    show_location = models.BooleanField(default=True)
    custom_text = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_label_template_by_branch"),
        ]

    def __str__(self):
        return self.name


class _PostableDocument(TenantModel):
    """Cabecalho de um documento que nasce rascunho e e confirmado depois.

    Entrada e saida compartilham o mesmo ciclo: enquanto e rascunho pode tudo,
    confirmado vira imutavel e so se desfaz por movimento inverso.
    """

    STATUS_DRAFT = "draft"
    STATUS_POSTED = "posted"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Rascunho"),
        (STATUS_POSTED, "Confirmado"),
        (STATUS_CANCELLED, "Cancelado"),
    ]

    location = models.ForeignKey(StockLocation, related_name="%(class)s_set", on_delete=models.PROTECT)
    effective_date = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="%(class)s_posted", on_delete=models.PROTECT
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="%(class)s_cancelled", on_delete=models.PROTECT
    )

    class Meta:
        abstract = True

    @property
    def is_editable(self):
        return self.status == self.STATUS_DRAFT


class StockEntry(_PostableDocument):
    supplier = models.CharField(max_length=160, blank=True)
    document_number = models.CharField(max_length=60, blank=True)

    class Meta:
        verbose_name = "entrada de estoque"
        verbose_name_plural = "entradas de estoque"
        ordering = ["-effective_date", "-created_at"]

    def __str__(self):
        return f"Entrada {self.document_number or self.id}"


class StockEntryItem(TenantModel):
    """Uma linha da entrada. Insumo + lote + validade distintos = linhas distintas."""

    entry = models.ForeignKey(StockEntry, related_name="items", on_delete=models.CASCADE)
    ingredient = models.ForeignKey("menu.Ingredient", related_name="entry_items", on_delete=models.PROTECT)
    # "2 pacotes de 5 kg": package_quantity=2, content_per_package=5, content_unit=kg.
    package_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    content_per_package = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    content_unit = models.CharField(max_length=12, blank=True)
    # Resultado da conversao, na unidade base do insumo. Gravado na confirmacao.
    base_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    supplier_lot = models.CharField(max_length=80, blank=True)
    manufactured_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    label_count = models.PositiveSmallIntegerField(default=1)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.ingredient} ({self.entry})"


class StockLot(TenantModel):
    """O lote fisico disponivel — a unidade que a etiqueta identifica."""

    STATUS_AVAILABLE = "available"
    STATUS_DEPLETED = "depleted"
    STATUS_BLOCKED = "blocked"
    STATUS_EXPIRED = "expired"
    STATUS_DISCARDED = "discarded"
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Disponivel"),
        (STATUS_DEPLETED, "Esgotado"),
        (STATUS_BLOCKED, "Bloqueado"),
        (STATUS_EXPIRED, "Vencido"),
        (STATUS_DISCARDED, "Descartado"),
    ]

    ingredient = models.ForeignKey("menu.Ingredient", related_name="lots", on_delete=models.PROTECT)
    location = models.ForeignKey(StockLocation, related_name="lots", on_delete=models.PROTECT)
    entry_item = models.ForeignKey(
        StockEntryItem, null=True, blank=True, related_name="lots", on_delete=models.SET_NULL
    )
    # Codigo imutavel impresso na etiqueta. Nunca reaproveitado: a etiqueta
    # colada na embalagem precisa continuar apontando para ESTE lote.
    code = models.CharField(max_length=40, db_index=True)
    supplier_lot = models.CharField(max_length=80, blank=True)
    entered_at = models.DateField()
    manufactured_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    initial_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    # Saldo materializado: o livro de movimentos continua sendo a fonte de
    # verdade, mas separar lote por lote no livro a cada consulta tornaria a
    # sugestao FIFO/FEFO cara demais. Atualizado na MESMA transacao.
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_AVAILABLE, db_index=True)
    opened_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["expires_at", "entered_at", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "code"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_stock_lot_code_by_account",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "ingredient", "status"]),
            models.Index(fields=["branch", "expires_at"]),
        ]

    def __str__(self):
        return f"{self.code} ({self.ingredient})"

    @staticmethod
    def build_code(ingredient):
        """Prefixo legivel do insumo + sufixo aleatorio.

        Uma sequencia por insumo seria mais bonita, mas exigiria serializar as
        entradas concorrentes so para numerar uma etiqueta. O sufixo aleatorio
        e unico sem coordenacao e continua curto o suficiente para caber
        impresso e ser conferido a olho.
        """
        prefix = "".join(ch for ch in (ingredient.name or "").upper() if ch.isalnum())[:3] or "LOT"
        return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


class StockExit(_PostableDocument):
    TYPE_CONSUMPTION = "consumption"
    TYPE_LOSS = "loss"
    TYPE_DISCARD = "discard"
    TYPE_TRANSFER = "transfer"
    TYPE_INTERNAL = "internal"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_CONSUMPTION, "Consumo manual"),
        (TYPE_LOSS, "Perda"),
        (TYPE_DISCARD, "Descarte"),
        (TYPE_TRANSFER, "Transferencia"),
        (TYPE_INTERNAL, "Uso interno"),
        (TYPE_OTHER, "Outro"),
    ]

    exit_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=TYPE_CONSUMPTION)
    # Estrategia efetivamente aplicada na separacao — copiada da configuracao
    # no momento da sugestao, para o documento explicar a propria escolha
    # mesmo se a configuracao mudar depois.
    picking_strategy = models.CharField(max_length=8, choices=StockSettings.PICKING_CHOICES, blank=True)
    reason = models.TextField()
    require_label_scan = models.BooleanField(default=False)
    destination = models.ForeignKey(
        StockLocation, null=True, blank=True, related_name="incoming_transfers", on_delete=models.PROTECT
    )

    class Meta:
        verbose_name = "saida de estoque"
        verbose_name_plural = "saidas de estoque"
        ordering = ["-effective_date", "-created_at"]

    def __str__(self):
        return f"Saida {self.id}"


class StockExitItem(TenantModel):
    exit = models.ForeignKey(StockExit, related_name="items", on_delete=models.CASCADE)
    ingredient = models.ForeignKey("menu.Ingredient", related_name="exit_items", on_delete=models.PROTECT)
    requested_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    fulfilled_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.ingredient} ({self.exit})"


class StockAllocation(TenantModel):
    """Como uma linha de saida foi distribuida entre lotes."""

    exit_item = models.ForeignKey(StockExitItem, related_name="allocations", on_delete=models.CASCADE)
    lot = models.ForeignKey(StockLot, related_name="allocations", on_delete=models.PROTECT)
    suggested_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    confirmed_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    scanned_code = models.CharField(max_length=40, blank=True)
    scanned_at = models.DateTimeField(null=True, blank=True)
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="stock_scans", on_delete=models.PROTECT
    )
    is_substitution = models.BooleanField(default=False)
    substitution_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.lot} x {self.suggested_quantity}"

    @property
    def is_confirmed(self):
        return bool(self.scanned_at)


class StockMovement(TenantModel):
    TYPE_IN = "in"
    TYPE_OUT = "out"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_SALE = "sale"
    TYPE_INVENTORY = "inventory"
    TYPE_REVERSAL = "reversal"

    TYPE_CHOICES = [
        (TYPE_IN, "In"),
        (TYPE_OUT, "Out"),
        (TYPE_ADJUSTMENT, "Adjustment"),
        (TYPE_SALE, "Sale"),
        (TYPE_INVENTORY, "Inventory"),
        (TYPE_REVERSAL, "Reversal"),
    ]

    ingredient = models.ForeignKey("menu.Ingredient", related_name="stock_movements", on_delete=models.PROTECT)
    location = models.ForeignKey(StockLocation, related_name="movements", on_delete=models.PROTECT)
    lot = models.ForeignKey(StockLot, null=True, blank=True, related_name="movements", on_delete=models.PROTECT)
    entry = models.ForeignKey(StockEntry, null=True, blank=True, related_name="movements", on_delete=models.SET_NULL)
    exit = models.ForeignKey(StockExit, null=True, blank=True, related_name="movements", on_delete=models.SET_NULL)
    order_item = models.ForeignKey("orders.OrderItem", null=True, blank=True, related_name="stock_movements", on_delete=models.SET_NULL)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="stock_movements", on_delete=models.PROTECT)
    movement_type = models.CharField(max_length=24, choices=TYPE_CHOICES, db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.TextField(blank=True)
    # Chave da ORIGEM do consumo: um item de pedido, um componente daquele item
    # e o evento que o gerou. E o que impede a segunda chamada de baixar tudo
    # de novo — a baixa era disparada tanto no envio para a cozinha quanto no
    # pagamento, e cada lote enviado percorria o pedido inteiro outra vez.
    source_key = models.CharField(max_length=200, blank=True, db_index=True)
    # A composicao congelada no momento da baixa (receita, rendimento, unidade,
    # fator de conversao). Editar a ficha tecnica depois nao pode reescrever o
    # que ja saiu do estoque.
    source_snapshot = models.JSONField(default=dict, blank=True)
    reversal_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="reversals",
        on_delete=models.PROTECT,
    )

    class Meta:
        constraints = [
            # Vazio nao conflita (movimento manual nao tem origem automatica);
            # preenchido, e unico na conta.
            models.UniqueConstraint(
                fields=["account", "source_key"],
                condition=~models.Q(source_key="") & models.Q(deleted_at__isnull=True),
                name="unique_stock_movement_source_key",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "ingredient", "created_at"]),
            models.Index(fields=["branch", "movement_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.ingredient} {self.quantity}"
