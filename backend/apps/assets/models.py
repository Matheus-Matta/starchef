import uuid
from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Asset(TenantModel):
    STATUS_IN_STOCK = "IN_STOCK"
    STATUS_IN_USE = "IN_USE"
    STATUS_IN_MAINTENANCE = "IN_MAINTENANCE"
    STATUS_BROKEN = "BROKEN"
    STATUS_LOANED = "LOANED"
    STATUS_TRANSFERRED = "TRANSFERRED"
    STATUS_INACTIVE = "INACTIVE"
    STATUS_DISPOSED = "DISPOSED"
    STATUS_LOST = "LOST"
    STATUS_STOLEN = "STOLEN"

    STATUS_CHOICES = [
        (STATUS_IN_STOCK, "Em Estoque / Aguardando Instalação"),
        (STATUS_IN_USE, "Em Uso / Operação"),
        (STATUS_IN_MAINTENANCE, "Em Manutenção"),
        (STATUS_BROKEN, "Com Avaria / Inoperante"),
        (STATUS_LOANED, "Emprestado / Comodato"),
        (STATUS_TRANSFERRED, "Transferido"),
        (STATUS_INACTIVE, "Desativado"),
        (STATUS_DISPOSED, "Baixado / Descartado"),
        (STATUS_LOST, "Extraviado"),
        (STATUS_STOLEN, "Furtado / Roubado"),
    ]

    asset_code = models.CharField(
        max_length=40,
        db_index=True,
        help_text="Código patrimonial interno (ex: EQ-000001)."
    )
    product = models.ForeignKey(
        "menu.Product",
        related_name="assets",
        on_delete=models.PROTECT,
        help_text="Produto mestre correspondente."
    )
    nfe = models.ForeignKey(
        "inbound_nfe.InboundNFe",
        null=True,
        blank=True,
        related_name="assets",
        on_delete=models.SET_NULL,
        help_text="NF-e de compra de origem."
    )
    nfe_item = models.ForeignKey(
        "inbound_nfe.InboundNFeItem",
        null=True,
        blank=True,
        related_name="assets",
        on_delete=models.SET_NULL
    )
    receipt = models.ForeignKey(
        "stock.GoodsReceipt",
        null=True,
        blank=True,
        related_name="assets",
        on_delete=models.SET_NULL
    )
    supplier_cnpj = models.CharField(max_length=14, blank=True)
    supplier_name = models.CharField(max_length=180, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    brand = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=120, blank=True, db_index=True, help_text="Número de série de fábrica.")
    patrimony_number = models.CharField(max_length=60, blank=True, help_text="Número de plaqueta física adicional.")
    manufacturer_code = models.CharField(max_length=60, blank=True)

    location = models.ForeignKey(
        "stock.StockLocation",
        related_name="assets",
        on_delete=models.PROTECT,
        help_text="Localização física atual do equipamento."
    )
    responsible_person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="responsible_assets",
        on_delete=models.SET_NULL,
        help_text="Colaborador responsável pelo ativo."
    )
    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default=STATUS_IN_USE,
        db_index=True
    )

    warranty_start_date = models.DateField(null=True, blank=True)
    warranty_end_date = models.DateField(null=True, blank=True, db_index=True)
    warranty_months = models.PositiveIntegerField(default=12)
    warranty_provider = models.CharField(max_length=180, blank=True)
    warranty_terms = models.TextField(blank=True)

    installation_date = models.DateField(null=True, blank=True)
    useful_life_months = models.PositiveIntegerField(null=True, blank=True)
    qr_code_token = models.CharField(max_length=64, blank=True, unique=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Ativo Patrimonial"
        verbose_name_plural = "Ativos Patrimoniais"
        ordering = ["asset_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "asset_code"],
                name="unique_asset_code_by_account"
            )
        ]

    def save(self, *args, **kwargs):
        if not self.qr_code_token:
            self.qr_code_token = uuid.uuid4().hex
        if not self.asset_code:
            # Gerar próximo código patrimonial EQ-XXXXXX por conta
            last_asset = Asset.all_objects.filter(account=self.account).order_by("-created_at").first()
            next_num = 1
            if last_asset and last_asset.asset_code and last_asset.asset_code.startswith("EQ-"):
                try:
                    next_num = int(last_asset.asset_code.split("-")[1]) + 1
                except (IndexError, ValueError):
                    next_num = 1
            self.asset_code = f"EQ-{next_num:06d}"
        super().save(*args, **kwargs)

    @property
    def name(self):
        return self.product.name if self.product else ""

    def __str__(self):
        return f"{self.asset_code} - {self.name} ({self.get_status_display()})"


class AssetLocationHistory(TenantModel):
    asset = models.ForeignKey(
        Asset,
        related_name="location_history",
        on_delete=models.CASCADE
    )
    from_location = models.ForeignKey(
        "stock.StockLocation",
        null=True,
        blank=True,
        related_name="assets_transferred_from",
        on_delete=models.SET_NULL
    )
    to_location = models.ForeignKey(
        "stock.StockLocation",
        related_name="assets_transferred_to",
        on_delete=models.PROTECT
    )
    moved_at = models.DateTimeField(auto_now_add=True)
    moved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="asset_transfers",
        on_delete=models.PROTECT
    )
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Histórico de Localização do Ativo"
        verbose_name_plural = "Históricos de Localizações dos Ativos"
        ordering = ["-moved_at"]

    def __str__(self):
        return f"{self.asset.asset_code}: {self.from_location} → {self.to_location}"


class AssetDisposal(TenantModel):
    DISPOSAL_SCRAPPED = "SCRAPPED"
    DISPOSAL_SOLD = "SOLD"
    DISPOSAL_DONATED = "DONATED"
    DISPOSAL_LOST = "LOST"
    DISPOSAL_STOLEN = "STOLEN"
    DISPOSAL_IRREPARABLE = "IRREPARABLE"
    DISPOSAL_OTHER = "OTHER"

    DISPOSAL_CHOICES = [
        (DISPOSAL_SCRAPPED, "Sucata / Descarte"),
        (DISPOSAL_SOLD, "Vendido"),
        (DISPOSAL_DONATED, "Doado"),
        (DISPOSAL_LOST, "Extraviado"),
        (DISPOSAL_STOLEN, "Furtado / Roubado"),
        (DISPOSAL_IRREPARABLE, "Sem Reparo / Danificado"),
        (DISPOSAL_OTHER, "Outro"),
    ]

    asset = models.OneToOneField(
        Asset,
        related_name="disposal",
        on_delete=models.CASCADE
    )
    disposal_type = models.CharField(
        max_length=25,
        choices=DISPOSAL_CHOICES,
        default=DISPOSAL_SCRAPPED
    )
    disposed_at = models.DateTimeField(auto_now_add=True)
    sale_value = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="authorized_asset_disposals",
        on_delete=models.PROTECT
    )
    reason = models.CharField(max_length=255)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Baixa Patrimonial"
        verbose_name_plural = "Baixas Patrimoniais"
        ordering = ["-disposed_at"]

    def __str__(self):
        return f"Baixa {self.asset.asset_code} ({self.get_disposal_type_display()})"
