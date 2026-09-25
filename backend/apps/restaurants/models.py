from django.conf import settings
from django.contrib.auth.hashers import PBKDF2PasswordHasher, identify_hasher
from django.db import models

from apps.core.models import TenantBaseModel, TenantModel


class Restaurant(TenantBaseModel):
    STOCK_DEDUCTION_PAYMENT = "payment"
    STOCK_DEDUCTION_KITCHEN = "kitchen"
    STOCK_DEDUCTION_CHOICES = [
        (STOCK_DEDUCTION_PAYMENT, "No pagamento"),
        (STOCK_DEDUCTION_KITCHEN, "No envio à cozinha"),
    ]
    legal_name = models.CharField(max_length=180)
    trade_name = models.CharField(max_length=180, db_index=True)
    # CNPJ opcional: nulos não conflitam no índice único (vários restaurantes
    # podem ficar sem CNPJ). Vazio é normalizado para null no serializer.
    cnpj = models.CharField(max_length=18, unique=True, null=True, blank=True)
    state_registration = models.CharField(max_length=40, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    district = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=16, blank=True)
    logo = models.ImageField(upload_to="restaurants/logos/", blank=True)
    logo_image = models.ForeignKey(
        "images.Image",
        null=True,
        blank=True,
        related_name="restaurant_logos",
        on_delete=models.SET_NULL,
    )
    default_service_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    require_open_cash_register = models.BooleanField(default=True)
    # Senha de autorização de ações do caixa (ex.: aprovar sangria/divergência).
    # Armazenada como PBKDF2-SHA256 — nunca em texto puro nem exposta na API.
    # O app Flutter sincroniza essa hash para autorização offline.
    cash_action_password = models.CharField(max_length=255, blank=True, default="")
    stock_deduction_timing = models.CharField(
        max_length=20, choices=STOCK_DEDUCTION_CHOICES, default=STOCK_DEDUCTION_PAYMENT
    )
    # Quantas comandas podem sentar na mesma mesa. Era um improviso com a
    # `Table.capacity` (lugares) só no PDV; agora é regra do restaurante e o
    # servidor a garante. 0 = sem limite.
    max_commands_per_table = models.PositiveIntegerField(default=4)
    # Janela, em segundos, entre "enviar para a cozinha" e a comanda sair de
    # fato (KDS/impressora). Dentro dela cancelar item ou pedido não pede a
    # senha do caixa nem gera cupom de cancelamento — nada chegou à produção.
    # 0 = desligada (comportamento antigo: sai na hora).
    cancellation_grace_seconds = models.PositiveIntegerField(default=0)
    # Quanto tempo o operador ainda pode CANCELAR um item DEPOIS de ele ter
    # chegado à produção. Passou disso, a remoção é recusada.
    #
    # É outra pergunta, e por isso outro campo. `cancellation_grace_seconds`
    # ATRASA o envio: dentro dele nada chegou à cozinha e cancelar é de graça.
    # Este conta do despacho para frente, quando o prato JÁ está sendo feito —
    # e o que ele protege é o trabalho do cozinheiro e o insumo que já foi.
    #
    # 0 = desligado, e é o padrão de propósito: toda instalação que já existe
    # continua podendo cancelar a qualquer momento até alguém decidir o
    # contrário. Uma regra nova que nasce ligada tranca operação no dia do
    # deploy, sem ninguém ter pedido.
    item_cancel_window_seconds = models.PositiveIntegerField(default=0)
    # O CÓDIGO DE QUEM LANÇOU, num aparelho compartilhado.
    #
    # Ligado, o app do garçom pede um código antes de criar pedido ou lançar item,
    # e grava em `metafields`. O caso é o totem no salão: vários garçons usando a
    # MESMA sessão, e sem isso todo lançamento do dia fica no nome do mesmo login.
    #
    # É ATRIBUIÇÃO, NÃO AUTENTICAÇÃO: o código não é conferido contra cadastro
    # nenhum e não dá permissão de nada. Ver `apps.orders.operator_code`.
    #
    # Nasce desligado: uma exigência nova que nasce ligada tranca o lançamento no
    # dia do deploy, com o salão cheio e ninguém sabendo que código digitar.
    require_operator_code = models.BooleanField(
        default=False,
        help_text="Pedir o código do operador antes de criar pedido ou lançar item (app do garçom).",
    )
    operational_settings = models.JSONField(default=dict, blank=True)
    fiscal_settings = models.JSONField(default=dict, blank=True)
    print_settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["trade_name"]

    def __str__(self):
        return self.trade_name

    def set_cash_action_password(self, raw_password):
        """Recebe a senha escolhida pelo operador e guarda somente seu hash."""
        if not raw_password:
            self.cash_action_password = ""
            return
        hasher = PBKDF2PasswordHasher()
        self.cash_action_password = hasher.encode(str(raw_password), hasher.salt())

    @staticmethod
    def _cash_action_password_is_encoded(value):
        # PBKDF2 precisa ser reconhecido mesmo quando settings de teste usam
        # apenas MD5 para acelerar senhas de usuários. Outros hashes Django
        # existentes são preservados para não transformar uma hash em senha.
        try:
            decoded = PBKDF2PasswordHasher().decode(value)
            return bool(decoded["salt"] and decoded["hash"] and decoded["iterations"] > 0)
        except (AssertionError, TypeError, ValueError):
            try:
                identify_hasher(value)
                return True
            except ValueError:
                return False

    def save(self, *args, **kwargs):
        # O serializer da API já transforma a senha, mas o Admin, imports e
        # scripts também podem atribuir o campo diretamente. Centralizar esta
        # proteção no modelo impede que "123" seja persistido como se já fosse
        # uma hash Django — situação em que toda validação recusaria a senha.
        update_fields = kwargs.get("update_fields")
        writes_password = self._state.adding or update_fields is None or "cash_action_password" in update_fields
        if (
            writes_password
            and self.cash_action_password
            and not self._cash_action_password_is_encoded(self.cash_action_password)
        ):
            self.set_cash_action_password(self.cash_action_password)
        super().save(*args, **kwargs)


class Branch(TenantBaseModel):
    STOCK_DEDUCTION_PAYMENT = "payment"
    STOCK_DEDUCTION_KITCHEN = "kitchen"

    STOCK_DEDUCTION_CHOICES = [
        (STOCK_DEDUCTION_PAYMENT, "On payment"),
        (STOCK_DEDUCTION_KITCHEN, "On kitchen send"),
    ]

    restaurant = models.ForeignKey(Restaurant, related_name="branches", on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    cnpj = models.CharField(max_length=18, blank=True)
    state_registration = models.CharField(max_length=40, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    district = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=16, blank=True)
    opening_hours = models.JSONField(default=dict, blank=True)
    default_service_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    require_open_cash_register = models.BooleanField(default=True)
    stock_deduction_timing = models.CharField(
        max_length=20,
        choices=STOCK_DEDUCTION_CHOICES,
        default=STOCK_DEDUCTION_PAYMENT,
    )
    print_settings = models.JSONField(default=dict, blank=True)
    fiscal_settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["restaurant__trade_name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "name"], name="unique_branch_name_by_restaurant"),
        ]
        indexes = [
            models.Index(fields=["restaurant", "is_active"]),
        ]

    def __str__(self):
        return f"{self.restaurant} - {self.name}"


class TableSector(TenantModel):
    name = models.CharField(max_length=80)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_table_sector_by_branch"),
        ]

    def __str__(self):
        return self.name


class Table(TenantModel):
    STATUS_FREE = "free"
    STATUS_OCCUPIED = "occupied"
    STATUS_RESERVED = "reserved"
    STATUS_CLEANING = "cleaning"

    STATUS_CHOICES = [
        (STATUS_FREE, "Free"),
        (STATUS_OCCUPIED, "Occupied"),
        (STATUS_RESERVED, "Reserved"),
        (STATUS_CLEANING, "Waiting cleaning"),
    ]

    sector = models.ForeignKey(TableSector, related_name="tables", on_delete=models.PROTECT)
    number = models.CharField(max_length=20)
    # Payload escaneavel no PDV (codigo de barras + QR codificam isto). Auto = number
    # quando vazio (definido no serializer). Unico por filial, como o number.
    code = models.CharField(max_length=40, blank=True)
    capacity = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_FREE, db_index=True)
    current_order_id = models.UUIDField(null=True, blank=True, db_index=True)
    joined_to = models.ForeignKey(
        "self", null=True, blank=True, related_name="joined_tables", on_delete=models.SET_NULL
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["sector__display_order", "number"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "number"], name="unique_table_number_by_branch"),
            models.UniqueConstraint(
                fields=["branch", "code"],
                condition=models.Q(code__gt=""),
                name="unique_table_code_by_branch",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "status"]),
        ]

    def save(self, *args, **kwargs):
        # Code escaneavel padrao = numero da mesa quando nao informado.
        if not self.code and self.number:
            self.code = str(self.number)
        super().save(*args, **kwargs)

    @property
    def esta_ocupada(self):
        """Tem gente sentada aqui? Quem responde são as comandas, não o campo.

        A mesa está ocupada enquanto houver cartão vinculado a ela COM O QUE
        COBRAR. Cartão sem nada a cobrar não ocupa mesa nenhuma: ele já foi
        embora, e a mesa que continua marcada some do salão — o garçom a vê
        ocupada, o cliente a vê vazia.

        `reserved` e `cleaning` NÃO são deriváveis: são decisão de pessoa, não
        consequência do consumo, e por isso continuam no campo. Esta
        propriedade responde só pela dimensão que o consumo determina.
        """
        from apps.core.tenant import tenant_context
        from apps.orders.command_billing import em_uso_subquery

        # Mesma razão de `Command.em_uso`: o manager é escopado por conta, e
        # fora de um request não há conta no ar. Sem isto a mesa responderia
        # "livre" em tarefa de fundo e comando de manage.py — em silêncio.
        with tenant_context(self.account_id):
            return (
                self.active_commands.annotate(tem_pendente=em_uso_subquery())
                .filter(tem_pendente=True)
                .exists()
            )

    def __str__(self):
        return f"Table {self.number}"


class Command(TenantModel):
    """Comanda reutilizavel (padrao self-service / Graal).

    Cartao fisico numerado com codigo de barras + QR. O `number` e o identificador
    humano impresso (unico POR RESTAURANTE — pode ir 1..N em cada restaurante),
    distinto do `id` (UUID). O `code` e o payload escaneavel (barcode/QR codificam
    isto). Enquanto vinculada a um pedido aberto fica OCCUPIED; ao pagar, e zerada
    e volta a FREE para reuso.
    """

    STATUS_FREE = "free"
    STATUS_OCCUPIED = "occupied"

    STATUS_CHOICES = [
        (STATUS_FREE, "Free"),
        (STATUS_OCCUPIED, "Occupied"),
    ]

    number = models.PositiveIntegerField()
    code = models.CharField(max_length=40, blank=True)
    customer_name = models.CharField(max_length=120, blank=True)
    # `status` NAO e coluna: e propriedade, calculada do consumo. Ver `status`
    # e `em_uso` mais abaixo.
    current_order_id = models.UUIDField(null=True, blank=True, db_index=True)
    current_table = models.ForeignKey(
        "restaurants.Table",
        null=True,
        blank=True,
        related_name="active_commands",
        on_delete=models.SET_NULL,
    )
    is_active = models.BooleanField(default=True)
    # OS CAMPOS ADICIONAIS DO CARTÃO, herdados pelo pedido que nascer dele.
    #
    # É aqui que o código de quem abriu a comanda fica: o pedido só nasce no
    # caixa, horas depois, e sem guardar no cartão o rastro de quem anotou se
    # perderia no caminho.
    metafields = models.JSONField(default=dict, blank=True, help_text="Campos adicionais livres. Dicionário raso, valores escalares curtos.")

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "number"], name="unique_command_number_by_restaurant"),
            models.UniqueConstraint(
                fields=["restaurant", "code"],
                condition=models.Q(code__gt=""),
                name="unique_command_code_by_restaurant",
            ),
        ]
    def save(self, *args, **kwargs):
        # Numero auto (sequencial por restaurante) e code escaneavel padrao quando
        # nao informados — cobre API, admin e criacao em lote. Import tardio evita
        # ciclo models <-> services.
        if not self.number and self.restaurant_id:
            from apps.restaurants.services import next_command_number

            self.number = next_command_number(self.restaurant)
        if not self.code and self.number:
            from apps.restaurants.services import default_command_code

            self.code = default_command_code(self.number)
        super().save(*args, **kwargs)

    @property
    def em_uso(self):
        """O cartão está em uso? Pergunta ao consumo — não há campo a consultar.

        "Em uso" é TER O QUE COBRAR. Isto já foi uma coluna, gravada por quem
        mexia nas anotações, e uma cópia gravada em oito lugares é uma cópia
        que um dia diverge. Divergiu: um caminho de saída esquecia de liberar,
        o cartão ficava marcado como ocupado sem nada a receber, e sumia do
        salão levando a mesa junto — sem nada estourar em lugar nenhum.

        Agora não há o que esquecer de atualizar. O custo é uma consulta por
        cartão; quem lista muitos usa a anotação do queryset
        (`CommandViewSet`), que responde por todos de uma vez.
        """
        from apps.core.tenant import tenant_context
        from apps.orders.command_billing import command_has_pending_items

        # A anotação da listagem, quando existe, já trouxe a resposta do banco.
        contados = getattr(self, "pendentes", None)
        if contados is not None:
            return contados > 0
        if self.pk is None:
            return False
        # A CONTA PRECISA SER A DO CARTÃO, e não a que estiver no ar.
        #
        # O manager de `CommandItem` é escopado por conta, e a middleware LIMPA
        # a conta ao terminar o request. Sem entrar no contexto do próprio
        # cartão, esta propriedade responde "livre" para qualquer cartão lido
        # fora de um request — numa tarefa de fundo, num comando de manage.py,
        # num sinal pós-commit — e responde isso em silêncio, que é o pior
        # jeito de errar sobre dinheiro.
        with tenant_context(self.account_id):
            if command_has_pending_items(self.pk):
                return True
            # UM CARTÃO PRESO A UMA CONTA ABERTA TAMBÉM ESTÁ EM USO, mesmo sem
            # anotação nenhuma. É o fluxo antigo, em que a comanda abria o
            # pedido: o consumo mora no pedido, não no cartão, e olhar só as
            # anotações devolveria à gaveta um cartão que está numa conta viva.
            #
            # O estado do PEDIDO é conferido de propósito: `current_order_id`
            # sobrevive a contas pagas e canceladas em bases antigas, e um id
            # velho deixaria o cartão ocupado para sempre.
            from apps.orders.models import Order

            if not self.current_order_id:
                return False
            return Order.all_objects.filter(
                pk=self.current_order_id,
                status__in=[Order.STATUS_OPEN, Order.STATUS_AWAITING_PAYMENT],
            ).exists()

    @property
    def status(self):
        """`free` ou `occupied`, calculado — a API continua respondendo igual.

        Mantido com o mesmo nome e os mesmos valores de antes de propósito: o
        PDV, o app do garçom e o painel leem este campo, e trocar o nome
        obrigaria os três a atualizar juntos. O que mudou é onde a resposta
        nasce.
        """
        return self.STATUS_OCCUPIED if self.em_uso else self.STATUS_FREE

    def __str__(self):
        return f"Comanda {self.number}"


class CommandMovementLog(TenantModel):
    ACTION_LINKED = "linked"
    ACTION_UNLINKED = "unlinked"
    ACTION_TRANSFERRED = "transferred"

    ACTION_CHOICES = [
        (ACTION_LINKED, "Linked to table"),
        (ACTION_UNLINKED, "Unlinked from table"),
        (ACTION_TRANSFERRED, "Transferred to another table"),
    ]

    command = models.ForeignKey(Command, on_delete=models.CASCADE, related_name="movement_logs")
    table = models.ForeignKey(
        "restaurants.Table", null=True, blank=True, on_delete=models.SET_NULL, related_name="command_movement_logs"
    )
    waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="command_movements_made",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    from_table = models.ForeignKey(
        "restaurants.Table", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["command", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} - Command {self.command_id} -> Table {self.table_id}"


class DeliveryZone(TenantModel):
    name = models.CharField(max_length=120)
    min_radius_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_radius_km = models.DecimalField(max_digits=8, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_minutes = models.PositiveIntegerField(default=45)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["min_radius_km"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_delivery_zone_by_branch"),
        ]

    def __str__(self):
        return f"{self.name} (até {self.max_radius_km}km)"


class Deliveryman(TenantModel):
    VEHICLE_BIKE = "bike"
    VEHICLE_MOTORCYCLE = "motorcycle"
    VEHICLE_CAR = "car"
    VEHICLE_FOOT = "foot"

    VEHICLE_CHOICES = [
        (VEHICLE_BIKE, "Bike"),
        (VEHICLE_MOTORCYCLE, "Motorcycle"),
        (VEHICLE_CAR, "Car"),
        (VEHICLE_FOOT, "On foot"),
    ]

    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, blank=True)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_CHOICES, default=VEHICLE_MOTORCYCLE)
    vehicle_plate = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_deliveryman_by_branch"),
        ]

    def __str__(self):
        return self.name
