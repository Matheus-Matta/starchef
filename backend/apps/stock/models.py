import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class StockLocation(TenantModel):
    TYPE_STORAGE = "STORAGE"
    TYPE_KITCHEN = "KITCHEN"
    TYPE_BAR = "BAR"
    TYPE_MAINTENANCE = "MAINTENANCE"
    TYPE_DISPOSAL = "DISPOSAL"
    TYPE_OTHER = "OTHER"

    TYPE_CHOICES = [
        (TYPE_STORAGE, "Estoque Central / Depósito"),
        (TYPE_KITCHEN, "Cozinha"),
        (TYPE_BAR, "Bar / Balcão"),
        (TYPE_MAINTENANCE, "Manutenção"),
        (TYPE_DISPOSAL, "Descarte"),
        (TYPE_OTHER, "Outro"),
    ]

    name = models.CharField(max_length=120)
    location_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_STORAGE,
        help_text="Tipo operacional do local de armazenamento."
    )
    parent_location = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.SET_NULL,
        help_text="Local pai para hierarquia (ex: Freezer 1 dentro da Cozinha)."
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Local de Estoque"
        verbose_name_plural = "Locais de Estoque"
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_stock_location_by_branch"),
        ]

    def __str__(self):
        return self.name


class Supplier(TenantModel):
    """Fornecedor reutilizavel pelos insumos e documentos de entrada da conta."""

    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="supplier_set",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=160)
    legal_name = models.CharField(max_length=180, blank=True)
    tax_id = models.CharField(max_length=18, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_supplier_name_by_account",
            ),
        ]

    def __str__(self):
        return self.name


class StockSettings(TenantModel):
    """Configuracao do estoque da CONTA.

    FIFO/FEFO, obrigatoriedade de validade, bloqueio de vencido e de saldo
    negativo sao politica da empresa, nao de cada unidade: o mesmo insumo
    vence do mesmo jeito em qualquer armazem. Uma configuracao por filial
    obrigava a repetir a mesma decisao em cada uma e deixava a rede
    operando com regras diferentes sem ninguem perceber.

    Quem localiza o estoque continua sendo o ARMAZEM (`StockLocation`).
    """

    # Cadastro da conta: sobrescreve o FK obrigatorio do TenantModel.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )

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
            # Uma por conta. A condicao existe porque o projeto usa exclusao
            # logica: sem ela, uma configuracao apagada bloquearia para
            # sempre a criacao de outra.
            models.UniqueConstraint(
                fields=["account"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_stock_settings_by_account",
            ),
        ]

    def __str__(self):
        return f"Estoque - {self.account}"


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
    supplier = models.ForeignKey(
        Supplier,
        null=True,
        blank=True,
        related_name="entry_items",
        on_delete=models.PROTECT,
    )
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

class GoodsReceipt(TenantModel):
    STATUS_DRAFT = "DRAFT"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_DIVERGENT = "DIVERGENT"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Em Conferência"),
        (STATUS_CONFIRMED, "Confirmado"),
        (STATUS_DIVERGENT, "Confirmado com Divergência"),
        (STATUS_CANCELLED, "Cancelado"),
    ]

    invoice = models.ForeignKey(
        "inbound_nfe.InboundNFe",
        null=True,
        blank=True,
        related_name="goods_receipts",
        on_delete=models.PROTECT,
        help_text="NF-e de origem da mercadoria."
    )
    receipt_number = models.CharField(
        max_length=40,
        blank=True,
        help_text="Identificador único da conferência (ex: REC-000045)."
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Data e hora física do recebimento."
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="goods_receipts",
        on_delete=models.PROTECT,
        help_text="Usuário/conferente que realizou o recebimento."
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_CONFIRMED,
        db_index=True
    )
    location = models.ForeignKey(
        "stock.StockLocation",
        null=True,
        blank=True,
        related_name="goods_receipts",
        on_delete=models.PROTECT,
        help_text="Local de estoque de entrada."
    )
    notes = models.TextField(
        blank=True,
        help_text="Observações gerais da conferência e recebimento."
    )

    class Meta:
        verbose_name = "Recebimento de Mercadorias"
        verbose_name_plural = "Recebimentos de Mercadorias"
        ordering = ["-received_at"]

    def __str__(self):
        return f"Recebimento #{self.receipt_number or self.id}"


class GoodsReceiptItem(TenantModel):
    receipt = models.ForeignKey(
        GoodsReceipt,
        related_name="items",
        on_delete=models.CASCADE
    )
    nfe_item = models.ForeignKey(
        "inbound_nfe.InboundNFeItem",
        null=True,
        blank=True,
        related_name="receipt_items",
        on_delete=models.SET_NULL
    )
    product = models.ForeignKey(
        "menu.Product",
        related_name="receipt_items",
        on_delete=models.PROTECT
    )
    expected_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        help_text="Quantidade declarada na NF-e convertida para a unidade de estoque."
    )
    received_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        help_text="Quantidade física conferida/pesada no recebimento."
    )
    difference_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        help_text="Divergência: recebido - esperado."
    )
    accepted_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        help_text="Quantidade efetivamente aceita para estoque."
    )
    rejected_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        help_text="Quantidade rejeitada/devolvida ao fornecedor."
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        help_text="Custo unitário real da mercadoria recebida."
    )
    total_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )
    lot_number = models.CharField(
        max_length=60,
        blank=True,
        help_text="Número do lote do fabricante/fornecedor."
    )
    manufacturing_date = models.DateField(
        null=True,
        blank=True,
        help_text="Data de fabricação do lote."
    )
    expiration_date = models.DateField(
        null=True,
        blank=True,
        help_text="Data de validade do lote."
    )
    serials = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de números de série gerados para itens patrimoniais."
    )
    notes = models.TextField(
        blank=True,
        help_text="Motivo da divergência ou observações do item."
    )

    class Meta:
        verbose_name = "Item de Recebimento"
        verbose_name_plural = "Itens de Recebimento"

    def __str__(self):
        return f"{self.product} ({self.received_quantity})"


class InventoryLot(TenantModel):
    STATUS_ACTIVE = "ACTIVE"
    STATUS_CONSUMED = "CONSUMED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_BLOCKED = "BLOCKED"
    STATUS_DISCARDED = "DISCARDED"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Ativo / Disponível"),
        (STATUS_CONSUMED, "Esgotado"),
        (STATUS_EXPIRED, "Vencido"),
        (STATUS_BLOCKED, "Bloqueado / Quarentena"),
        (STATUS_DISCARDED, "Descartado"),
    ]

    product = models.ForeignKey(
        "menu.Product",
        related_name="inventory_lots",
        on_delete=models.PROTECT
    )
    lot_number = models.CharField(
        max_length=60,
        db_index=True,
        help_text="Número ou identificador do lote."
    )
    supplier_cnpj = models.CharField(max_length=14, blank=True)
    supplier_name = models.CharField(max_length=180, blank=True)
    nfe = models.ForeignKey(
        "inbound_nfe.InboundNFe",
        null=True,
        blank=True,
        related_name="inventory_lots",
        on_delete=models.SET_NULL
    )
    receipt = models.ForeignKey(
        GoodsReceipt,
        null=True,
        blank=True,
        related_name="inventory_lots",
        on_delete=models.SET_NULL
    )
    receipt_item = models.ForeignKey(
        GoodsReceiptItem,
        null=True,
        blank=True,
        related_name="inventory_lots",
        on_delete=models.SET_NULL
    )
    location = models.ForeignKey(
        StockLocation,
        related_name="inventory_lots",
        on_delete=models.PROTECT
    )
    manufacturing_date = models.DateField(
        null=True,
        blank=True
    )
    expiration_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Data de validade para controle FEFO."
    )
    received_at = models.DateTimeField(
        auto_now_add=True
    )
    initial_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0
    )
    available_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        db_index=True
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0
    )
    total_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True
    )

    class Meta:
        verbose_name = "Lote de Estoque"
        verbose_name_plural = "Lotes de Estoque"
        ordering = ["expiration_date", "received_at"]
        indexes = [
            models.Index(fields=["branch", "product", "status", "expiration_date"]),
        ]

    def __str__(self):
        return f"{self.product} - Lote {self.lot_number} (Disp: {self.available_quantity})"


class StockMovement(TenantModel):
    # Tipos unificados e padronizados
    TYPE_PURCHASE_ENTRY = "PURCHASE_ENTRY"
    TYPE_SALE_OUTPUT = "SALE_OUTPUT"
    TYPE_PRODUCTION_CONSUMPTION = "PRODUCTION_CONSUMPTION"
    TYPE_TRANSFER_IN = "TRANSFER_IN"
    TYPE_TRANSFER_OUT = "TRANSFER_OUT"
    TYPE_LOSS = "LOSS"
    TYPE_BREAKAGE = "BREAKAGE"
    TYPE_EXPIRATION = "EXPIRATION"
    TYPE_RETURN_TO_SUPPLIER = "RETURN_TO_SUPPLIER"
    TYPE_CUSTOMER_RETURN = "CUSTOMER_RETURN"
    TYPE_INVENTORY_ADJUSTMENT_POSITIVE = "INVENTORY_ADJUSTMENT_POSITIVE"
    TYPE_INVENTORY_ADJUSTMENT_NEGATIVE = "INVENTORY_ADJUSTMENT_NEGATIVE"
    TYPE_INITIAL_BALANCE = "INITIAL_BALANCE"
    TYPE_ASSET_DISPOSAL = "ASSET_DISPOSAL"
    TYPE_NFE_CANCELLATION_REVERSAL = "NFE_CANCELLATION_REVERSAL"

    # Retrocompatibilidade
    TYPE_IN = "in"
    TYPE_OUT = "out"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_SALE = "sale"
    TYPE_INVENTORY = "inventory"
    TYPE_REVERSAL = "reversal"

    TYPE_CHOICES = [
        (TYPE_REVERSAL, "Reversal (Legado)"),
        (TYPE_PURCHASE_ENTRY, "Entrada por Compra (NF-e)"),
        (TYPE_NFE_CANCELLATION_REVERSAL, "Estorno por Cancelamento de NF-e"),
        (TYPE_SALE_OUTPUT, "Saída por Venda"),
        (TYPE_PRODUCTION_CONSUMPTION, "Consumo em Ficha Técnica"),
        (TYPE_TRANSFER_IN, "Transferência (Entrada)"),
        (TYPE_TRANSFER_OUT, "Transferência (Saída)"),
        (TYPE_LOSS, "Perda / Desperdício"),
        (TYPE_BREAKAGE, "Quebra de Reutilizável / Utensílio"),
        (TYPE_EXPIRATION, "Baixa por Validade Vencida"),
        (TYPE_RETURN_TO_SUPPLIER, "Devolução ao Fornecedor"),
        (TYPE_CUSTOMER_RETURN, "Retorno de Cliente"),
        (TYPE_INVENTORY_ADJUSTMENT_POSITIVE, "Ajuste de Inventário (+)"),
        (TYPE_INVENTORY_ADJUSTMENT_NEGATIVE, "Ajuste de Inventário (-)"),
        (TYPE_INITIAL_BALANCE, "Implantação de Saldo"),
        (TYPE_ASSET_DISPOSAL, "Baixa Patrimonial"),
        # Legados
        (TYPE_IN, "Entrada (Legado)"),
        (TYPE_OUT, "Saída (Legado)"),
        (TYPE_ADJUSTMENT, "Ajuste (Legado)"),
        (TYPE_SALE, "Venda (Legado)"),
        (TYPE_INVENTORY, "Inventário (Legado)"),
    ]

    product = models.ForeignKey(
        "menu.Product",
        null=True,
        blank=True,
        related_name="stock_movements",
        on_delete=models.PROTECT
    )
    ingredient = models.ForeignKey(
        "menu.Ingredient",
        null=True,
        blank=True,
        related_name="stock_movements",
        on_delete=models.PROTECT
    )
    location = models.ForeignKey(
        StockLocation,
        related_name="movements",
        on_delete=models.PROTECT
    )
    lot = models.ForeignKey(StockLot, null=True, blank=True, related_name="movements", on_delete=models.PROTECT)
    entry = models.ForeignKey(StockEntry, null=True, blank=True, related_name="movements", on_delete=models.SET_NULL)
    exit = models.ForeignKey(StockExit, null=True, blank=True, related_name="movements", on_delete=models.SET_NULL)
    order_item = models.ForeignKey(
        "orders.OrderItem",
        null=True,
        blank=True,
        related_name="stock_movements",
        on_delete=models.SET_NULL
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="stock_movements",
        on_delete=models.PROTECT
    )
    movement_type = models.CharField(
        max_length=40,
        choices=TYPE_CHOICES,
        db_index=True
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        help_text="Quantidade movimentada (positiva para entradas, negativa/positiva conforme tipo)."
    )
    stock_unit = models.CharField(
        max_length=12,
        default="UN"
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0
    )
    total_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )
    nfe = models.ForeignKey(
        "inbound_nfe.InboundNFe",
        null=True,
        blank=True,
        related_name="stock_movements",
        on_delete=models.SET_NULL
    )
    nfe_item = models.ForeignKey(
        "inbound_nfe.InboundNFeItem",
        null=True,
        blank=True,
        related_name="stock_movements",
        on_delete=models.SET_NULL
    )
    receipt = models.ForeignKey(
        GoodsReceipt,
        null=True,
        blank=True,
        related_name="stock_movements",
        on_delete=models.SET_NULL
    )
    receipt_item = models.ForeignKey(
        GoodsReceiptItem,
        null=True,
        blank=True,
        related_name="stock_movements",
        on_delete=models.SET_NULL
    )
    inventory_lot = models.ForeignKey(
        InventoryLot,
        null=True,
        blank=True,
        related_name="movements",
        on_delete=models.SET_NULL
    )
    source_location = models.ForeignKey(
        StockLocation,
        null=True,
        blank=True,
        related_name="transfers_out",
        on_delete=models.SET_NULL
    )
    destination_location = models.ForeignKey(
        StockLocation,
        null=True,
        blank=True,
        related_name="transfers_in",
        on_delete=models.SET_NULL
    )
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
        verbose_name = "Movimento de Estoque"
        verbose_name_plural = "Movimentos de Estoque"
        ordering = ["-created_at"]
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
            models.Index(fields=["branch", "product", "created_at"]),
            models.Index(fields=["branch", "ingredient", "created_at"]),
            models.Index(fields=["branch", "movement_type", "created_at"]),
        ]

    def __str__(self):
        item_name = self.product.name if self.product else (self.ingredient.name if self.ingredient else "Item")
        return f"{self.movement_type} - {item_name}: {self.quantity} {self.stock_unit}"
