from django.db import models

from apps.core.models import TenantModel


class FiscalProfile(TenantModel):
    """Grupo tributario reutilizavel por produtos (CFOP/CSOSN/NCM + aliquotas).

    E um cadastro DA CONTA, nao do restaurante: o mesmo "Bebida" ou "Prato
    padrao" vale para todas as unidades, do mesmo jeito que as categorias do
    cardapio. Quem escolhe o perfil e o PRODUTO (``menu.Product.fiscal_profile``),
    numa relacao 1:N — um perfil serve N produtos.

    Os valores default sao "em branco"/zero de proposito: cada conta configura
    conforme seu enquadramento. Simples Nacional costuma usar CSOSN (ex.: 102) e
    aliquotas zeradas no cupom.
    """

    # Compartilhado entre restaurantes (reutilizavel): o vinculo de restaurante
    # e opcional. Sobrescreve o FK obrigatorio do TenantModel — mesmo padrao de
    # `menu.ProductCategory` / `menu.ProductAddon`.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=120)
    ncm = models.CharField(max_length=8, blank=True, help_text="Codigo NCM do produto.")
    cest = models.CharField(max_length=7, blank=True)
    cfop = models.CharField(max_length=4, default="5102", help_text="CFOP de venda (ex.: 5102).")
    origem = models.CharField(max_length=1, default="0", help_text="Origem da mercadoria (0=nacional).")
    csosn = models.CharField(max_length=3, blank=True, help_text="CSOSN (Simples Nacional, ex.: 102).")
    cst_icms = models.CharField(max_length=2, blank=True, help_text="CST ICMS (regime normal).")
    icms_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    pis_cst = models.CharField(max_length=2, default="49")
    pis_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    cofins_cst = models.CharField(max_length=2, default="49")
    cofins_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    approx_tax_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=0, help_text="Tributos aprox. (Lei 12.741) em %."
    )
    is_default = models.BooleanField(default=False, help_text="Marca o perfil sugerido no cadastro de produtos.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            # Nome unico por CONTA (e nao mais por filial): o perfil e um
            # cadastro reutilizavel, entao "Bebida" e um so em toda a conta.
            models.UniqueConstraint(fields=["account", "name"], name="unique_fiscal_profile_by_account"),
        ]

    def __str__(self):
        return self.name


class FiscalConfig(TenantModel):
    """Configuracao fiscal da filial (emitente + parametros de emissao).

    Campos SECRETOS/EXTERNOS ficam em branco ate a configuracao real:
    `csc_token` (CSC da NFC-e), `certificate_ref` (certificado A1) e as URLs.
    """

    PROVIDER_MANUAL = "manual"  # sem transmissao SEFAZ (scaffold/contingencia)
    PROVIDER_FOCUS_NFE = "focus_nfe"
    PROVIDER_CHOICES = [
        (PROVIDER_MANUAL, "Manual (sem transmissao)"),
        (PROVIDER_FOCUS_NFE, "Focus NFe"),
    ]

    FOCUS_SYNC_NOT_CONFIGURED = "not_configured"
    FOCUS_SYNC_PENDING = "pending"
    FOCUS_SYNC_SYNCED = "synced"
    FOCUS_SYNC_ERROR = "error"
    FOCUS_SYNC_CHOICES = [
        (FOCUS_SYNC_NOT_CONFIGURED, "Nao configurado"),
        (FOCUS_SYNC_PENDING, "Aguardando sincronizacao"),
        (FOCUS_SYNC_SYNCED, "Sincronizado"),
        (FOCUS_SYNC_ERROR, "Erro de sincronizacao"),
    ]

    MODEL_NFCE = "65"
    MODEL_NFE = "55"
    MODEL_SAT = "59"
    MODEL_CHOICES = [
        (MODEL_NFCE, "NFC-e (modelo 65)"),
        (MODEL_NFE, "NF-e (modelo 55)"),
        (MODEL_SAT, "SAT/CF-e (modelo 59)"),
    ]

    ENV_PRODUCTION = "1"
    ENV_HOMOLOGATION = "2"
    ENV_CHOICES = [(ENV_PRODUCTION, "Producao"), (ENV_HOMOLOGATION, "Homologacao")]

    CRT_SIMPLES = "1"
    CRT_SIMPLES_EXCESSO = "2"
    CRT_NORMAL = "3"
    CRT_CHOICES = [
        (CRT_SIMPLES, "Simples Nacional"),
        (CRT_SIMPLES_EXCESSO, "Simples Nacional - excesso de sublimite"),
        (CRT_NORMAL, "Regime Normal"),
    ]

    provider = models.CharField(
        max_length=40,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_MANUAL,
        help_text="Provedor de emissao.",
    )
    document_model = models.CharField(max_length=2, choices=MODEL_CHOICES, default=MODEL_NFCE)
    environment = models.CharField(max_length=1, choices=ENV_CHOICES, default=ENV_HOMOLOGATION)
    crt = models.CharField(max_length=1, choices=CRT_CHOICES, default=CRT_SIMPLES)
    series = models.PositiveIntegerField(default=1)
    next_number = models.PositiveIntegerField(default=1, help_text="Proximo numero sequencial (nNF).")

    # Emitente
    cnpj = models.CharField(max_length=18, blank=True)
    ie = models.CharField(max_length=20, blank=True, help_text="Inscricao Estadual.")
    corporate_name = models.CharField(max_length=180, blank=True, help_text="Razao social.")
    trade_name = models.CharField(max_length=180, blank=True, help_text="Nome fantasia.")
    address_line = models.CharField(max_length=255, blank=True)
    address_number = models.CharField(max_length=20, blank=True, help_text="Numero do endereco do emitente.")
    district = models.CharField(max_length=120, blank=True, help_text="Bairro do endereco do emitente.")
    city = models.CharField(max_length=120, blank=True)
    city_ibge = models.CharField(max_length=7, blank=True, help_text="Codigo IBGE do municipio.")
    uf = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=9, blank=True)

    # Integracao NFC-e / certificado — EM BRANCO ate configurar.
    csc_id = models.CharField(max_length=6, blank=True, help_text="ID do CSC (idToken).")
    csc_token = models.CharField(max_length=64, blank=True, help_text="CSC (segredo) da NFC-e.")
    qr_base_url = models.URLField(blank=True, help_text="URL de consulta da NFC-e da UF.")
    portal_url = models.URLField(blank=True, help_text="URL do portal para consulta por chave.")
    certificate_ref = models.CharField(max_length=255, blank=True, help_text="Referencia ao certificado A1.")
    provider_token = models.CharField(
        max_length=255, blank=True, help_text="Credencial/token do integrador fiscal (ex.: Focus NFe)."
    )
    focus_company_id = models.CharField(max_length=80, blank=True, db_index=True)
    focus_token_production = models.CharField(max_length=255, blank=True)
    focus_token_homologation = models.CharField(max_length=255, blank=True)
    focus_certificate_base64 = models.TextField(blank=True)
    focus_certificate_password = models.CharField(max_length=255, blank=True)
    focus_sync_status = models.CharField(
        max_length=24,
        choices=FOCUS_SYNC_CHOICES,
        default=FOCUS_SYNC_NOT_CONFIGURED,
    )
    focus_sync_error = models.TextField(blank=True)
    focus_synced_at = models.DateTimeField(null=True, blank=True)
    focus_remote_data = models.JSONField(default=dict, blank=True)

    default_profile = models.ForeignKey(
        FiscalProfile, null=True, blank=True, related_name="+", on_delete=models.SET_NULL
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch"], name="unique_fiscal_config_by_branch"),
        ]

    def __str__(self):
        return f"FiscalConfig {self.trade_name or self.branch_id}"

    @property
    def is_ready(self):
        """True quando o minimo para emissao real esta preenchido (senao, scaffold)."""
        if self.provider == self.PROVIDER_FOCUS_NFE:
            token = (
                self.focus_token_production
                if self.environment == self.ENV_PRODUCTION
                else self.focus_token_homologation
            )
            return bool(self.cnpj and self.uf and token)
        return bool(self.cnpj and self.uf and self.csc_token and self.certificate_ref)


class Invoice(TenantModel):
    PHASE_RECEIPT = "receipt"
    PHASE_FISCAL = "fiscal"

    STATUS_DRAFT = "draft"
    STATUS_PENDING = "pending"  # documento montado, aguardando autorizacao (parte em branco)
    STATUS_ISSUED = "issued"  # autorizado pela SEFAZ
    STATUS_CANCELLED = "cancelled"
    STATUS_ERROR = "error"

    EMISSION_NORMAL = "1"
    EMISSION_CONTINGENCY = "9"  # contingencia offline (tpEmis): provider real falhou/indisponivel
    EMISSION_TYPE_CHOICES = [
        (EMISSION_NORMAL, "Normal"),
        (EMISSION_CONTINGENCY, "Contingencia offline"),
    ]

    order = models.OneToOneField("orders.Order", related_name="invoice", on_delete=models.PROTECT)
    phase = models.CharField(max_length=20, default=PHASE_RECEIPT)
    status = models.CharField(max_length=20, default=STATUS_DRAFT, db_index=True)
    provider = models.CharField(max_length=80, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True, db_index=True)

    # Identificacao do documento
    document_model = models.CharField(max_length=2, blank=True)
    series = models.PositiveIntegerField(null=True, blank=True)
    number = models.CharField(max_length=60, blank=True)  # nNF
    environment = models.CharField(max_length=1, blank=True)
    crt = models.CharField(max_length=1, blank=True)
    emission_type = models.CharField(
        max_length=1, choices=EMISSION_TYPE_CHOICES, default=EMISSION_NORMAL, help_text="tpEmis da chave de acesso."
    )
    access_key = models.CharField(max_length=44, blank=True, db_index=True)

    # Emitente (snapshot no momento da emissao)
    emitter_cnpj = models.CharField(max_length=18, blank=True)
    emitter_name = models.CharField(max_length=180, blank=True)

    # Destinatario / consumidor (NFC-e permite "nao identificado")
    recipient_cpf = models.CharField(max_length=14, blank=True)
    recipient_name = models.CharField(max_length=180, blank=True)

    # Totais
    products_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_approx_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # QR Code / consulta
    qr_code_data = models.TextField(blank=True)
    consult_url = models.URLField(blank=True)

    # ── Preenchido pela SEFAZ/provedor (EM BRANCO no scaffold) ──────────────
    authorization_protocol = models.CharField(max_length=60, blank=True)
    authorized_at = models.DateTimeField(null=True, blank=True)
    digest_value = models.CharField(max_length=64, blank=True)  # assinatura/digest

    fiscal_payload = models.JSONField(default=dict, blank=True)
    xml_content = models.TextField(blank=True)
    danfe_url = models.URLField(blank=True)
    error_message = models.TextField(blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["branch", "status", "created_at"]),
            models.Index(fields=["access_key"]),
        ]

    def __str__(self):
        return f"Invoice {self.number or self.id}"


class InvoiceItem(TenantModel):
    """Item fiscal do documento, com o detalhamento tributario por linha."""

    invoice = models.ForeignKey(Invoice, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("menu.Product", null=True, blank=True, related_name="invoice_items", on_delete=models.SET_NULL)
    line_number = models.PositiveIntegerField(default=1)
    code = models.CharField(max_length=60, blank=True)
    description = models.CharField(max_length=180)
    ncm = models.CharField(max_length=8, blank=True)
    cest = models.CharField(max_length=7, blank=True)
    cfop = models.CharField(max_length=4, blank=True)
    csosn = models.CharField(max_length=3, blank=True)
    cst_icms = models.CharField(max_length=2, blank=True)
    origem = models.CharField(max_length=1, default="0")
    unit = models.CharField(max_length=6, default="UN")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    icms_base = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    icms_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    icms_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pis_cst = models.CharField(max_length=2, default="49")
    pis_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    pis_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cofins_cst = models.CharField(max_length=2, default="49")
    cofins_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    cofins_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    approx_tax_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["line_number"]

    def __str__(self):
        return f"{self.description} ({self.invoice_id})"
