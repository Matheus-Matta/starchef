"""O que um cliente consumiu — a parte que `OrderItem` e `CommandItem` têm igual.

A comanda é um bloco de notas: ela anota o que o cliente consumiu e manda para
a produção, sem existir pedido nenhum. O pedido nasce no caixa e recebe os
itens pendentes das comandas que vão ser pagas juntas.

São dois donos diferentes para a MESMA coisa — um item de consumo, com preço,
setor de produção, estado de cozinha e histórico. Esta classe é essa coisa.
Cada modelo concreto acrescenta só o que é dele: o pedido de um lado, a comanda
do outro.

## Por que os campos de relação NÃO estão aqui

Numa base abstrata do Django, `related_name` precisa conter `%(class)s` — o
Django não deixa duas subclasses reivindicarem o mesmo acessório reverso. Se
`launched_by` viesse daqui, o `related_name` de `OrderItem` deixaria de ser
`order_items_launched` e viraria `orderitems_launched`, quebrando todo o código
que já lê esse acessório e produzindo uma migração inteira de renomeação sem
nenhum ganho.

Então a base carrega os campos ESCALARES e, principalmente, o COMPORTAMENTO —
que é o que de fato se quer compartilhar. As chaves estrangeiras são declaradas
em cada modelo concreto, com o nome reverso que já é o dele.
"""
import uuid

from django.db import models

from apps.core.models import TenantModel


class ConsumptionItemStatus:
    """Os estados de PRODUÇÃO de um item consumido.

    Fora da classe do modelo de propósito: o KDS, a impressão e os dois PDVs
    comparam contra estes valores, e importá-los de `OrderItem` faria o item da
    comanda depender do modelo de pedido para saber o próprio estado.
    """

    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    COMPED = "comped"

    CHOICES = [
        (PENDING, "Pending"),
        (QUEUED, "Queued during grace period"),
        (SENT, "Sent"),
        (PREPARING, "Preparing"),
        (READY, "Ready"),
        (DELIVERED, "Delivered"),
        (CANCELLED, "Cancelled"),
        (COMPED, "Comped"),
    ]

    #: Não entra em conta: cancelado não é consumo, cortesia não é cobrança.
    FORA_DA_CONTA = [CANCELLED, COMPED]


class ConsumptionItem(TenantModel):
    """Um item consumido: o que é, quanto custa e em que pé está na produção."""

    STATUS_PENDING = ConsumptionItemStatus.PENDING
    STATUS_QUEUED = ConsumptionItemStatus.QUEUED
    STATUS_SENT = ConsumptionItemStatus.SENT
    STATUS_PREPARING = ConsumptionItemStatus.PREPARING
    STATUS_READY = ConsumptionItemStatus.READY
    STATUS_DELIVERED = ConsumptionItemStatus.DELIVERED
    STATUS_CANCELLED = ConsumptionItemStatus.CANCELLED
    STATUS_COMPED = ConsumptionItemStatus.COMPED
    STATUS_CHOICES = ConsumptionItemStatus.CHOICES

    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    variations = models.JSONField(default=list, blank=True)
    customer_note = models.TextField(blank=True)
    production_sector = models.CharField(max_length=20, db_index=True)
    status = models.CharField(
        max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    launched_at = models.DateTimeField(auto_now_add=True)
    sent_to_kitchen_at = models.DateTimeField(null=True, blank=True)
    preparation_started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    # QUEM REGISTROU ESTE ITEM, quando o login não responde isso.
    #
    # Fica na base abstrata porque a pergunta é a mesma no item do pedido e no da
    # comanda: um aparelho compartilhado (o totem do salão) lança nos dois, e o
    # rastro precisa acompanhar o item até o relatório — não o cabeçalho.
    #
    # O item é o ÚNICO lugar onde o código de quem lançou serve de verdade: num
    # pedido de uma hora de duração, três garçons anotam, e um código só no
    # cabeçalho atribuiria tudo ao primeiro.
    metafields = models.JSONField(default=dict, blank=True, help_text="Campos adicionais livres. Dicionário raso, valores escalares curtos.")

    class Meta:
        abstract = True
        ordering = ["launched_at"]

    def __str__(self):
        return f"{self.quantity} x {self.product}"

    @property
    def variation_suffix(self):
        """Sufixo ' - Variacao A, Variacao B' para colar no nome do produto.

        A variacao descreve QUAL produto e (sabor, tamanho, ponto da carne),
        entao sai na mesma linha dele em toda nota impressa; quem vai para
        uma linha propria abaixo e o adicional. Fica no modelo, e nao no
        modulo de impressao, porque os templates HTML precisam do mesmo
        texto — duplicar a regra la ja tinha feito o cupom e o HTML da mesma
        nota divergirem.
        """
        nomes = []
        for variation in self.variations or []:
            nome = variation.get("name") if isinstance(variation, dict) else variation
            if nome:
                nomes.append(str(nome))
        return f" - {', '.join(nomes)}" if nomes else ""

    @property
    def conta_na_conta(self):
        """Este item entra no que o cliente vai pagar?

        Cancelado e cortesia continuam existindo — o histórico é o motivo de
        nada ser apagado —, mas não somam. A pergunta aparece em toda soma de
        comanda, de pedido e de conta agrupada, e escrevê-la à mão em cada uma
        foi o que já deixou um relatório cobrando cortesia.
        """
        return self.status not in ConsumptionItemStatus.FORA_DA_CONTA

    @property
    def foi_para_a_producao(self):
        """Já saiu ticket na impressora do setor para este item?

        É o que decide se cancelar custa um cupom de cancelamento na cozinha ou
        se é de graça.
        """
        return self.sent_to_kitchen_at is not None


class ProductionBatch(TenantModel):
    """Uma RODADA de produção: o que foi mandado junto para a cozinha.

    O pedido tem as dele, a comanda tem as dela, e as duas funcionam igual —
    número sequencial por dono, um serial que o ticket impresso carrega no
    `REF:`, e um `dispatch_at` que segura a rodada durante a carência de
    cancelamento do restaurante.

    Como em [ConsumptionItem], as chaves estrangeiras ficam no modelo concreto
    para não renomear os acessórios reversos que já existem.
    """

    STATUS_SCHEDULED = "scheduled"
    STATUS_SENT = "sent"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_SENT, "Sent"),
        (STATUS_DONE, "Done"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    serial = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    batch_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED
    )
    sent_at = models.DateTimeField()
    dispatch_at = models.DateTimeField(null=True, blank=True, db_index=True)
    printed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["batch_number"]

    @property
    def esperando_a_carencia(self):
        """A rodada existe mas ainda NÃO chegou à produção.

        Durante a carência do restaurante nada saiu na impressora nem apareceu
        no KDS, e cancelar é de graça. É a mesma pergunta nas duas frentes, e
        respondê-la olhando `dispatch_at` na mão em cada lugar já divergiu.
        """
        return self.status == self.STATUS_SCHEDULED
