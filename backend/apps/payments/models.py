from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TenantBaseModel, TenantModel

# Estados TERMINAIS de uma sessao de caixa: acabou, e o caixa esta livre para
# uma nova abertura. Fica em nivel de modulo porque o corpo de `class Meta` nao
# enxerga os atributos da classe que o contem — e a `UniqueConstraint` parcial
# da exclusividade precisa exatamente desta lista.
CASH_REGISTER_FINAL_STATUSES = ("closed", "closed_with_difference", "cancelled")


class CashStation(TenantBaseModel):
    restaurant = models.ForeignKey("restaurants.Restaurant", related_name="cash_stations", on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    operators = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="cash_stations")
    cash_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["restaurant", "code"], name="unique_cash_station_code_by_restaurant")]

    def __str__(self):
        return f"{self.restaurant} - {self.name}"


class PdvTerminal(TenantBaseModel):
    """O terminal fisico/instalacao de onde uma sessao de caixa foi aberta.

    O `device_identifier` antigo era texto livre — a web mandava
    `navigator.userAgent`, que identifica o navegador e nao a maquina (a
    propria MDN desaconselha usa-lo como identidade), e o Flutter nao mandava
    nada. Sem saber DE ONDE a sessao foi aberta nao da para cumprir a regra de
    exclusividade: "o mesmo usuario em outra maquina tambem sera bloqueado".

    A identidade e o UUID da INSTALACAO, gerado e guardado pelo cliente:
    - Flutter reusa o `nodeId` que a topologia local ja persiste;
    - Web gera com `crypto.randomUUID()` e guarda no perfil do navegador.

    Nao usamos MAC, IP nem hostname: nenhum e estavel, e todos sao dados do
    equipamento que nao precisamos guardar. Limpar o navegador cria uma
    instalacao nova — o que nao abre um segundo caixa, porque a exclusividade
    e garantida no servidor (e no Caixa Principal), nao no cliente.
    """

    TYPE_DESKTOP = "desktop"
    TYPE_WEB = "web"
    TYPE_MOBILE = "mobile"
    TYPE_CHOICES = [
        (TYPE_DESKTOP, "Desktop"),
        (TYPE_WEB, "Navegador"),
        (TYPE_MOBILE, "Aplicativo"),
    ]

    ROLE_PRINCIPAL = "principal"
    ROLE_SECONDARY = "secondary"
    ROLE_WEB = "web"
    ROLE_CHOICES = [
        (ROLE_PRINCIPAL, "Caixa Principal"),
        (ROLE_SECONDARY, "Caixa Secundario"),
        (ROLE_WEB, "Navegador"),
    ]

    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="pdv_terminals",
        on_delete=models.PROTECT,
    )
    installation_id = models.CharField(
        max_length=120,
        db_index=True,
        help_text="UUID da instalacao, gerado e persistido pelo proprio terminal.",
    )
    name = models.CharField(max_length=120, blank=True, help_text='Nome amigavel, ex.: "Balcao 01".')
    device_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=TYPE_DESKTOP)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_SECONDARY)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "installation_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "installation_id"],
                name="unique_pdv_terminal_installation_by_account",
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        """Como o terminal aparece nas mensagens de bloqueio."""
        return self.name or f"terminal {self.installation_id[:8]}"


class PaymentMethod(TenantModel):
    TYPE_CASH = "cash"
    TYPE_CARD = "card"
    TYPE_PIX = "pix"
    TYPE_VOUCHER = "voucher"
    TYPE_OTHER = "other"

    TYPE_CHOICES = [
        (TYPE_CASH, "Cash"),
        (TYPE_CARD, "Card"),
        (TYPE_PIX, "PIX"),
        (TYPE_VOUCHER, "Voucher"),
        (TYPE_OTHER, "Other"),
    ]

    name = models.CharField(max_length=80)
    method_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    requires_reference = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_payment_method_by_branch"),
        ]

    def __str__(self):
        return self.name


class Payment(TenantModel):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    CARD_DEBIT = "debit"
    CARD_CREDIT = "credit"
    CARD_SUBTYPE_CHOICES = [
        (CARD_DEBIT, "Débito"),
        (CARD_CREDIT, "Crédito"),
    ]

    order = models.ForeignKey("orders.Order", related_name="payments", on_delete=models.PROTECT)
    payment_method = models.ForeignKey(PaymentMethod, related_name="payments", on_delete=models.PROTECT)
    # Subtipo do cartão (débito/crédito) — obrigatório apenas quando o método é
    # cartão; para os demais métodos permanece vazio (STC-061).
    card_subtype = models.CharField(max_length=12, choices=CARD_SUBTYPE_CHOICES, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    change_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_APPROVED, db_index=True)
    idempotency_key = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_payment_idempotency_by_account",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "paid_at"]),
            models.Index(fields=["order", "status"]),
        ]

    def __str__(self):
        return f"{self.order} - {self.amount}"


class CashRegister(TenantModel):
    STATUS_PENDING_OPENING = "pending_opening"
    STATUS_OPEN = "open"
    STATUS_BLOCKED = "blocked"
    STATUS_PENDING_APPROVAL = "pending_manager_approval"
    STATUS_PENDING_CLOSING = "pending_closing"
    STATUS_CLOSED = "closed"
    STATUS_CLOSED_DIFFERENCE = "closed_with_difference"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING_OPENING, "Aguardando abertura"),
        (STATUS_OPEN, "Open"),
        (STATUS_BLOCKED, "Bloqueado"),
        (STATUS_PENDING_APPROVAL, "Aguardando aprovação gerencial"),
        (STATUS_PENDING_CLOSING, "Aguardando fechamento"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_CLOSED_DIFFERENCE, "Fechado com divergência"),
        (STATUS_CANCELLED, "Cancelado"),
    ]

    # Estados TERMINAIS: a sessão acabou e o caixa está livre para uma nova
    # abertura. Ponto único de verdade — a lista vivia repetida em views,
    # serializers, services e no Flutter, e uma cópia divergente
    # (`closed_difference` em vez de `closed_with_difference`) fazia um caixa
    # já fechado continuar parecendo aberto no terminal offline.
    FINAL_STATUSES = CASH_REGISTER_FINAL_STATUSES

    @classmethod
    def active_sessions(cls, queryset=None):
        """Sessões ainda não finalizadas — as que ocupam um caixa."""
        return (queryset if queryset is not None else cls.objects).exclude(status__in=cls.FINAL_STATUSES)

    @property
    def is_finished(self):
        return self.status in self.FINAL_STATUSES

    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="cash_registers_opened",
        on_delete=models.PROTECT,
    )
    cash_station = models.ForeignKey(CashStation, null=True, blank=True, related_name="sessions", on_delete=models.PROTECT)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="cash_registers_closed",
        on_delete=models.SET_NULL,
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    difference_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    station = models.CharField(max_length=120, default="PDV principal", db_index=True)
    device_identifier = models.CharField(max_length=255, blank=True)
    # Terminal que abriu e terminal que fechou. Os `*_terminal_label` são um
    # retrato do nome no momento da operação: renomear "Balcão 01" depois não
    # pode reescrever a auditoria de quem abriu o caixa naquele dia.
    opened_terminal = models.ForeignKey(
        PdvTerminal,
        null=True,
        blank=True,
        related_name="cash_registers_opened",
        on_delete=models.SET_NULL,
    )
    closed_terminal = models.ForeignKey(
        PdvTerminal,
        null=True,
        blank=True,
        related_name="cash_registers_closed",
        on_delete=models.SET_NULL,
    )
    opened_terminal_label = models.CharField(max_length=160, blank=True)
    closed_terminal_label = models.CharField(max_length=160, blank=True)
    opening_is_initial = models.BooleanField(default=False)
    pending_operation = models.CharField(max_length=24, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="cash_registers_approved", on_delete=models.SET_NULL)
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["branch", "status", "opened_at"]),
        ]
        constraints = [
            # A trava real da exclusividade. A checagem no serviço ("consulta e
            # depois cria") não resiste a duas aberturas simultâneas: as duas
            # transações leem "livre" antes de qualquer uma gravar. Só o banco
            # decide isso sem corrida — e um índice parcial é exatamente a
            # ferramenta para "no máximo uma linha ativa por caixa".
            models.UniqueConstraint(
                fields=["cash_station"],
                condition=Q(deleted_at__isnull=True) & ~Q(status__in=CASH_REGISTER_FINAL_STATUSES),
                name="unique_active_session_per_cash_station",
            ),
        ]

    def __str__(self):
        return f"Cash register {self.opened_at:%Y-%m-%d} - {self.branch}"


class CashMovement(TenantModel):
    TYPE_OPENING = "opening"
    TYPE_SALE = "sale"
    TYPE_WITHDRAWAL = "withdrawal"
    TYPE_SUPPLY = "supply"
    TYPE_CLOSING = "closing"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_REFUND = "refund"

    TYPE_CHOICES = [
        (TYPE_OPENING, "Opening"),
        (TYPE_SALE, "Sale"),
        (TYPE_WITHDRAWAL, "Withdrawal"),
        (TYPE_SUPPLY, "Supply"),
        (TYPE_CLOSING, "Closing"),
        (TYPE_ADJUSTMENT, "Adjustment"),
        (TYPE_REFUND, "Estorno em dinheiro"),
    ]

    cash_register = models.ForeignKey(CashRegister, related_name="movements", on_delete=models.PROTECT)
    payment = models.ForeignKey(Payment, null=True, blank=True, related_name="cash_movements", on_delete=models.SET_NULL)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="cash_movements", on_delete=models.PROTECT)
    movement_type = models.CharField(max_length=24, choices=TYPE_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField(blank=True)
    destination = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, default="approved", db_index=True)
    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="cash_movements_authorized", on_delete=models.SET_NULL)
    approved_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["cash_register", "movement_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.movement_type} - {self.amount}"
