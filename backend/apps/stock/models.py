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
        related_name="lots",
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

    # Retrocompatibilidade
    TYPE_IN = "in"
    TYPE_OUT = "out"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_SALE = "sale"
    TYPE_INVENTORY = "inventory"

    TYPE_CHOICES = [
        (TYPE_PURCHASE_ENTRY, "Entrada por Compra (NF-e)"),
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

    class Meta:
        verbose_name = "Movimento de Estoque"
        verbose_name_plural = "Movimentos de Estoque"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["branch", "product", "created_at"]),
            models.Index(fields=["branch", "ingredient", "created_at"]),
            models.Index(fields=["branch", "movement_type", "created_at"]),
        ]

    def __str__(self):
        item_name = self.product.name if self.product else (self.ingredient.name if self.ingredient else "Item")
        return f"{self.movement_type} - {item_name}: {self.quantity} {self.stock_unit}"

