from django.db import models
from django.conf import settings
from apps.core.models import TenantModel


class DFeSyncState(TenantModel):
    cnpj = models.CharField(
        max_length=14,
        blank=True,
        help_text="CNPJ utilizado na consulta DF-e."
    )

    environment = models.CharField(
        max_length=15,
        default="production",
        help_text="Ambiente: production ou homologation."
    )

    ult_nsu = models.CharField(
        max_length=15,
        default="000000000000000"
    )

    max_nsu = models.CharField(
        max_length=15,
        default="000000000000000"
    )

    last_cstat = models.CharField(
        max_length=3,
        blank=True
    )

    last_reason = models.TextField(
        blank=True
    )

    last_sync_at = models.DateTimeField(
        null=True,
        blank=True
    )

    next_allowed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    is_syncing = models.BooleanField(
        default=False
    )

    sync_error_count = models.PositiveIntegerField(
        default=0,
        help_text="Contagem de erros consecutivos de sincronização."
    )

    class Meta:
        verbose_name = "Estado de Sincronização DF-e"
        verbose_name_plural = "Estados de Sincronização DF-e"


class DFeDistributionDocument(TenantModel):
    """Armazena cada documento bruto (docZip) recebido do serviço NFeDistribuicaoDFe.
    O XML original é mantido permanentemente para auditoria e reprocessamento."""

    DOC_RES_NFE = "resNFe"
    DOC_PROC_NFE = "procNFe"
    DOC_RES_EVENTO = "resEvento"
    DOC_PROC_EVENTO = "procEventoNFe"
    DOC_UNKNOWN = "unknown"
    DOC_TYPE_CHOICES = [
        (DOC_RES_NFE, "Resumo NF-e"),
        (DOC_PROC_NFE, "NF-e Completa"),
        (DOC_RES_EVENTO, "Resumo Evento"),
        (DOC_PROC_EVENTO, "Evento Completo"),
        (DOC_UNKNOWN, "Desconhecido"),
    ]

    PROCESSING_PENDING = "pending"
    PROCESSING_OK = "ok"
    PROCESSING_ERROR = "error"
    PROCESSING_SKIPPED = "skipped"
    PROCESSING_CHOICES = [
        (PROCESSING_PENDING, "Pendente"),
        (PROCESSING_OK, "Processado"),
        (PROCESSING_ERROR, "Erro"),
        (PROCESSING_SKIPPED, "Ignorado"),
    ]

    nsu = models.CharField(
        max_length=15,
        db_index=True,
        help_text="NSU do documento na SEFAZ."
    )

    schema = models.CharField(
        max_length=100,
        blank=True,
        help_text="Atributo schema do docZip (ex: resNFe_v1.01.xsd)."
    )

    access_key = models.CharField(
        max_length=44,
        blank=True,
        db_index=True,
        help_text="Chave de acesso extraída do XML, quando disponível."
    )

    document_type = models.CharField(
        max_length=30,
        choices=DOC_TYPE_CHOICES,
        default=DOC_UNKNOWN,
        help_text="Tipo do documento identificado pelo schema."
    )

    xml = models.TextField(
        help_text="XML original descompactado. NUNCA apagar."
    )

    received_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Momento em que o documento foi recebido da SEFAZ."
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Momento em que o processamento foi concluído."
    )

    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_CHOICES,
        default=PROCESSING_PENDING
    )

    processing_error = models.TextField(
        blank=True,
        help_text="Mensagem de erro do último processamento."
    )

    class Meta:
        verbose_name = "Documento DF-e"
        verbose_name_plural = "Documentos DF-e"
        ordering = ["nsu"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "nsu"],
                name="unique_dfe_doc_by_account_nsu"
            )
        ]


class InboundNFe(TenantModel):
    STATUS_SUMMARY = "summary"
    STATUS_XML_AVAILABLE = "xml_available"
    STATUS_PENDING_MAPPING = "pending_mapping"
    STATUS_PENDING_RECEIPT = "pending_receipt"
    STATUS_RECEIVED = "received"
    STATUS_CANCELLED = "cancelled"

    DISTRIBUTION_SUMMARY = "summary"
    DISTRIBUTION_FULL = "full"

    XML_STATUS_SUMMARY_ONLY = "summary_only"
    XML_STATUS_FULL_XML_PENDING = "full_xml_pending"
    XML_STATUS_FULL_XML_AVAILABLE = "full_xml_available"
    XML_STATUS_FULL_XML_ERROR = "full_xml_error"

    MANIFEST_NONE = "none"
    MANIFEST_SCIENCE_PENDING = "science_pending"
    MANIFEST_SCIENCE_REGISTERED = "science_registered"
    MANIFEST_CONFIRMED = "confirmed"
    MANIFEST_UNKNOWN = "unknown_operation"
    MANIFEST_NOT_PERFORMED = "operation_not_performed"
    MANIFEST_ERROR = "manifestation_error"

    RECEIVING_NOT_STARTED = "not_started"
    RECEIVING_PENDING = "pending"
    RECEIVING_PARTIAL = "partial"
    RECEIVING_RECEIVED = "received"
    RECEIVING_DIVERGENT = "divergent"

    access_key = models.CharField(
        max_length=44,
        db_index=True
    )

    nsu = models.CharField(
        max_length=15,
        blank=True
    )

    number = models.CharField(
        max_length=20,
        blank=True
    )

    series = models.CharField(
        max_length=10,
        blank=True
    )

    issue_date = models.DateTimeField(
        null=True,
        blank=True
    )

    supplier_cnpj = models.CharField(
        max_length=14,
        blank=True
    )

    supplier_name = models.CharField(
        max_length=180,
        blank=True
    )

    total_products = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    total_invoice = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=30
    )

    distribution_type = models.CharField(
        max_length=20,
        default=DISTRIBUTION_SUMMARY
    )

    xml_status = models.CharField(
        max_length=30,
        default=XML_STATUS_SUMMARY_ONLY
    )

    manifestation_status = models.CharField(
        max_length=30,
        blank=True,
        default=MANIFEST_NONE
    )

    receiving_status = models.CharField(
        max_length=30,
        default=RECEIVING_NOT_STARTED
    )

    summary_xml = models.TextField(
        blank=True
    )

    full_xml = models.TextField(
        blank=True
    )

    stock_applied_at = models.DateTimeField(
        null=True,
        blank=True
    )

    stock_applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )

    class Meta:
        verbose_name = "NF-e de Entrada"
        verbose_name_plural = "NF-es de Entrada"
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "access_key"],
                name="unique_inbound_nfe_by_account"
            )
        ]


class NFeManifestation(TenantModel):
    """
    Armazena os eventos oficiais de Manifestação do Destinatário (TPEvento 210210, 210200, etc.)
    transmitidos ao webservice NFeRecepcaoEvento4 da SEFAZ.
    """
    STATUS_PENDING = "PENDING"
    STATUS_SIGNED = "SIGNED"
    STATUS_SENT = "SENT"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_REJECTED = "REJECTED"
    STATUS_ERROR = "ERROR"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendente"),
        (STATUS_SIGNED, "Assinado"),
        (STATUS_SENT, "Enviado"),
        (STATUS_ACCEPTED, "Aceito"),
        (STATUS_REJECTED, "Rejeitado"),
        (STATUS_ERROR, "Erro"),
    ]

    EVENT_SCIENCE = "science"
    EVENT_CONFIRM = "confirm"
    EVENT_UNKNOWN = "unknown"
    EVENT_NOT_PERFORMED = "not_performed"
    EVENT_TYPE_CHOICES = [
        (EVENT_SCIENCE, "Ciência da Operação"),
        (EVENT_CONFIRM, "Confirmação da Operação"),
        (EVENT_UNKNOWN, "Desconhecimento da Operação"),
        (EVENT_NOT_PERFORMED, "Operação não Realizada"),
    ]

    invoice = models.ForeignKey(
        InboundNFe,
        related_name="manifestations",
        on_delete=models.CASCADE
    )

    access_key = models.CharField(
        max_length=44,
        db_index=True
    )

    event_type = models.CharField(
        max_length=30,
        choices=EVENT_TYPE_CHOICES
    )

    event_code = models.CharField(
        max_length=6,
        help_text="Código do evento SEFAZ: 210210, 210200, 210220, 210240."
    )

    sequence = models.PositiveIntegerField(
        default=1,
        help_text="Número sequencial do evento (nSeqEvento)."
    )

    event_datetime = models.DateTimeField(
        help_text="Data e hora do evento timezone-aware."
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    sefaz_batch_status = models.CharField(
        max_length=10,
        blank=True,
        help_text="cStat do lote (retEnvEvento)."
    )

    sefaz_batch_reason = models.TextField(
        blank=True,
        help_text="xMotivo do lote."
    )

    sefaz_event_status = models.CharField(
        max_length=10,
        blank=True,
        help_text="cStat do evento individual (infEvento/cStat)."
    )

    sefaz_event_reason = models.TextField(
        blank=True,
        help_text="xMotivo do evento individual."
    )

    protocol = models.CharField(
        max_length=50,
        blank=True,
        help_text="Número de protocolo do registro do evento (nProt)."
    )

    request_xml = models.TextField(
        blank=True,
        help_text="XML enviado à SEFAZ assinado com XMLDSig."
    )

    response_xml = models.TextField(
        blank=True,
        help_text="XML bruto recebido na resposta da SEFAZ."
    )

    registered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Data/hora de registro do evento retornado pela SEFAZ (dhRegEvento)."
    )

    reason = models.TextField(
        blank=True,
        help_text="Justificativa (obrigatória para Operação não Realizada - 210240)."
    )

    history = models.JSONField(
        default=list,
        blank=True,
        help_text="Histórico de tentativas anteriores de envio do evento para auditoria."
    )

    class Meta:
        verbose_name = "Manifestação do Destinatário"
        verbose_name_plural = "Manifestações do Destinatário"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "invoice", "event_code", "sequence"],
                name="unique_manifestation_event_seq"
            )
        ]


class InboundNFeItem(TenantModel):
    invoice = models.ForeignKey(
        InboundNFe,
        related_name="items",
        on_delete=models.CASCADE
    )

    item_number = models.PositiveIntegerField()

    supplier_code = models.CharField(
        max_length=60,
        blank=True
    )

    ean = models.CharField(
        max_length=14,
        blank=True
    )

    description = models.CharField(
        max_length=255
    )

    ncm = models.CharField(
        max_length=8,
        blank=True
    )

    cfop = models.CharField(
        max_length=4,
        blank=True
    )

    commercial_unit = models.CharField(
        max_length=10,
        blank=True
    )

    commercial_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    commercial_unit_value = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    taxable_unit = models.CharField(
        max_length=10,
        blank=True
    )

    taxable_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    taxable_unit_value = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    product_total = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    discount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    freight = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    insurance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    other_expenses = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    ean_trib = models.CharField(
        max_length=14,
        blank=True,
        help_text="EAN tributário (cEANTrib)."
    )

    cest = models.CharField(
        max_length=7,
        blank=True,
        help_text="Código CEST do produto."
    )

    tax_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dados tributários (ICMS, PIS, COFINS, IPI) extraídos do XML."
    )

    ingredient = models.ForeignKey(
        "menu.Ingredient",
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    product = models.ForeignKey(
        "menu.Product",
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    conversion_factor = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=1
    )

    received_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True
    )

    stock_movement = models.OneToOneField(
        "stock.StockMovement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inbound_nfe_item"
    )

    class Meta:
        verbose_name = "Item da NF-e"
        verbose_name_plural = "Itens da NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "item_number"],
                name="unique_item_by_invoice"
            )
        ]


class SupplierItemMapping(TenantModel):
    supplier_cnpj = models.CharField(
        max_length=14,
        db_index=True
    )

    supplier_code = models.CharField(
        max_length=60,
        blank=True
    )

    supplier_description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Descrição original do produto na NF-e do fornecedor."
    )

    supplier_ean = models.CharField(
        max_length=14,
        blank=True
    )

    ingredient = models.ForeignKey(
        "menu.Ingredient",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplier_mappings"
    )

    product = models.ForeignKey(
        "menu.Product",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="supplier_mappings"
    )

    conversion_factor = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=1,
        help_text="Fator de conversão: 1 unidade fiscal = factor * unidade estoque."
    )

    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.0,
        help_text="Nível de confiança da correspondência (0-100%)."
    )

    confirmed_by_user = models.BooleanField(
        default=True,
        help_text="Se o vínculo foi validado/confirmado manualmente pelo usuário."
    )

    last_used_at = models.DateTimeField(
        auto_now=True
    )

    @classmethod
    def save_mapping(
        cls,
        account,
        supplier_cnpj,
        supplier_code,
        supplier_ean,
        defaults,
    ):
        """
        Salva ou atualiza mapeamento de fornecedor garantindo integridade.
        Se já existir mapeamento por código e/ou por EAN, consolida em um único
        registro sem violar as constraints unique_mapping_by_supplier_code
        e unique_mapping_by_supplier_ean.
        """
        code = (supplier_code or "").strip()
        ean = (supplier_ean or "").strip()
        cnpj = (supplier_cnpj or "").strip()
        if not cnpj or (not code and not ean):
            return None

        q = models.Q()
        if code:
            q |= models.Q(supplier_code=code)
        if ean:
            q |= models.Q(supplier_ean=ean)

        existing = list(cls.all_objects.filter(account=account, supplier_cnpj=cnpj).filter(q))

        if existing:
            primary = existing[0]
            for duplicate in existing[1:]:
                models.Model.delete(duplicate)

            if code:
                primary.supplier_code = code
            if ean:
                primary.supplier_ean = ean

            for k, v in defaults.items():
                setattr(primary, k, v)
            primary.save()
            return primary
        else:
            return cls.objects.create(
                account=account,
                supplier_cnpj=cnpj,
                supplier_code=code,
                supplier_ean=ean,
                **defaults,
            )

    class Meta:
        verbose_name = "Mapeamento de Fornecedor"
        verbose_name_plural = "Mapeamentos de Fornecedores"
        constraints = [
            models.UniqueConstraint(
                fields=["account", "supplier_cnpj", "supplier_code"],
                condition=~models.Q(supplier_code="") & models.Q(deleted_at__isnull=True),
                name="unique_mapping_by_supplier_code"
            ),
            models.UniqueConstraint(
                fields=["account", "supplier_cnpj", "supplier_ean"],
                condition=~models.Q(supplier_ean="") & models.Q(deleted_at__isnull=True),
                name="unique_mapping_by_supplier_ean"
            )
        ]


class DFeGlobalConfig(models.Model):
    """
    Configuração Global do Sistema para Sincronização e Regras DF-e/SEFAZ.
    Válida para todos os clientes e empresas (Modificada apenas pelo Administrador/Programador).
    """
    enable_cooldown_blocking = models.BooleanField(
        default=True,
        verbose_name="Ativar Bloqueio Preventivo de Cooldown",
        help_text="Se desmarcado, o sistema NÃO bloqueia novas requisições preventivamente. Útil para testes ou para contornar bloqueios.",
    )

    cooldown_interval_minutes = models.PositiveIntegerField(
        default=30,
        verbose_name="Intervalo Mínimo entre Consultas (minutos)",
        help_text="Tempo de espera recomendado entre consultas sem novos documentos (padrão: 30 a 60 min).",
    )

    cooldown_no_docs_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Cooldown para Nenhum Documento / cStat 137 (minutos)",
        help_text="Tempo de espera quando a SEFAZ informa que não há mais documentos na fila.",
    )

    cooldown_error_minutes = models.PositiveIntegerField(
        default=5,
        verbose_name="Cooldown para Erros Temporários (minutos)",
        help_text="Tempo de espera após falha de comunicação ou erro genérico.",
    )

    blocked_message_template = models.TextField(
        default="A última consulta foi realizada há menos de {interval} minutos. Para proteger seu CNPJ contra penalidades da SEFAZ, aguarde até {time} (faltam {minutes} min).",
        verbose_name="Mensagem de Bloqueio Preventivo",
        help_text="Texto exibido aos clientes na tela. Variáveis disponíveis: {time} (horário permitido), {minutes} (minutos restantes) e {interval} (intervalo configurado).",
    )

    blocked_cstat_656_message_template = models.TextField(
        default="Consulta bloqueada temporariamente por Consumo Indevido na SEFAZ. Próxima requisição permitida após às {time} (faltam {minutes} min).",
        verbose_name="Mensagem de Consumo Indevido (cStat 656)",
        help_text="Texto exibido aos clientes na tela quando a SEFAZ bloqueia por cStat 656. Variáveis disponíveis: {time} e {minutes}.",
    )

    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última Atualização")

    class Meta:
        verbose_name = "Configuração Global SEFAZ"
        verbose_name_plural = "Configurações Globais SEFAZ"

    def __str__(self):
        status_txt = "Bloqueio Ativo" if self.enable_cooldown_blocking else "Bloqueio Desativado (Livre)"
        return f"Configurações Globais DF-e/SEFAZ ({status_txt})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
