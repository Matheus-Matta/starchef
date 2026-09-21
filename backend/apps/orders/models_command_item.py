"""A comanda como BLOCO DE NOTAS: o que o cliente consumiu, sem pedido.

O cartão não abre pedido. Ele anota o consumo e manda para a produção como
qualquer outro item. O pedido nasce só no caixa, e recebe os itens **pendentes**
das comandas que vão ser pagas juntas.

É por isso que `CommandItem` existe em vez de o item nascer dentro de um pedido:
sem isso, escolher a comanda 13 já criava um pedido, desistir deixava um pedido
vazio prendendo o cartão, e pagar quatro comandas exigia quatro pedidos mais uma
consolidação que movia item por item — o caminho que não aguenta uma conta
grande.

O que é um item consumido (preço, setor, estado de cozinha, histórico) mora em
`ConsumptionItem`, compartilhado com `OrderItem`. Aqui fica só o que é da
comanda.
"""
from django.conf import settings
from django.db import models

from apps.orders.models_consumption import ConsumptionItem, ProductionBatch


class CommandBatch(ProductionBatch):
    """A rodada de produção DE UMA COMANDA.

    Igual à do pedido, e de propósito: o garçom lança três pratos e manda; sai
    um ticket com o número da rodada, e cancelar durante a carência do
    restaurante não custa cupom nenhum na cozinha.
    """

    command = models.ForeignKey(
        "restaurants.Command", related_name="batches", on_delete=models.CASCADE
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="command_batches_sent",
        on_delete=models.SET_NULL,
    )

    class Meta(ProductionBatch.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["command", "batch_number"],
                name="unique_batch_number_per_command",
            ),
        ]

    def __str__(self):
        return f"Rodada #{self.batch_number} — Comanda {self.command_id}"


class CommandItem(ConsumptionItem):
    """Uma anotação na comanda: o cliente consumiu isto.

    Nasce PENDENTE e sai da comanda de dois jeitos: COBRADO, quando o pedido
    que a incluiu é pago, ou CANCELADO, quando o item é removido ou a conta é
    cancelada. Nada é apagado — é isso que mantém o histórico do cartão depois
    de ele voltar para a gaveta e ser entregue a outro cliente.
    """

    # ── O estado NA COMANDA, que é financeiro e não de produção ─────────────
    #
    # São três, e não dois, porque "saiu da comanda" responde mal à pergunta
    # que o dono faz no fim do mês: o prato foi COBRADO ou foi EMBORA? Um
    # estado só juntaria a venda com a perda, e o relatório de quebra teria de
    # adivinhar a diferença pelo pedido — que pode nem existir mais.
    #
    # Só o PENDENTE entra numa conta. Os outros dois são finais.

    #: Aberto na comanda: entra na próxima conta que incluir o cartão.
    STATUS_PENDENTE = "pending"
    #: Cobrado — o pedido que o incluiu foi pago. É venda.
    STATUS_COBRADO = "billed"
    #: Saiu sem ser cobrado: item cancelado, cortesia, ou a conta foi cancelada.
    #: É perda, e o relatório precisa enxergar isso separado da venda.
    STATUS_CANCELADO = "cancelled"

    COMMAND_STATUS_CHOICES = [
        (STATUS_PENDENTE, "Pendente na comanda"),
        (STATUS_COBRADO, "Cobrado"),
        (STATUS_CANCELADO, "Cancelado na comanda"),
    ]

    #: Os estados que tiram o item da comanda. Nenhum deles volta para a conta.
    STATUS_FINALIZADOS = [STATUS_COBRADO, STATUS_CANCELADO]

    command = models.ForeignKey(
        "restaurants.Command", related_name="command_items", on_delete=models.PROTECT
    )

    # A MESA EM QUE FOI CONSUMIDO — retrato, não vínculo vivo.
    #
    # A comanda anda pelo salão: o cliente troca de mesa, e a mesa atual dela é
    # `Command.current_table`. Guardar aqui onde CADA item foi consumido é o que
    # responde "o que saiu na mesa 4 hoje" depois de a comanda ter mudado de
    # lugar — e derivar isso da comanda depois daria a resposta errada.
    table = models.ForeignKey(
        "restaurants.Table",
        null=True,
        blank=True,
        related_name="command_items",
        on_delete=models.SET_NULL,
    )

    command_status = models.CharField(
        max_length=16,
        choices=COMMAND_STATUS_CHOICES,
        default=STATUS_PENDENTE,
        db_index=True,
    )
    # "Quando saiu da comanda" é a pergunta seguinte em qualquer conferência, e
    # derivá-la de `updated_at` seria adivinhação: `updated_at` muda por
    # qualquer motivo.
    command_closed_at = models.DateTimeField(null=True, blank=True)

    batch = models.ForeignKey(
        CommandBatch,
        null=True,
        blank=True,
        related_name="items",
        on_delete=models.SET_NULL,
    )
    product = models.ForeignKey(
        "menu.Product", related_name="command_items", on_delete=models.PROTECT
    )
    # Coluna atual no quadro do KDS. O card da comanda e o do pedido convivem no
    # mesmo quadro — o que muda é só o rótulo de origem que a tela mostra.
    kds_column = models.ForeignKey(
        "kitchen.KdsColumn",
        null=True,
        blank=True,
        related_name="command_items",
        on_delete=models.SET_NULL,
    )
    launched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="command_items_launched",
        on_delete=models.SET_NULL,
    )
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="command_items_voided",
        on_delete=models.SET_NULL,
    )

    class Meta(ConsumptionItem.Meta):
        indexes = [
            models.Index(fields=["branch", "production_sector", "status"]),
            # A consulta mais quente do sistema: "o que esta comanda tem aberto
            # agora". Ela roda ao passar o cartão, ao montar a conta e a cada
            # atualização da tela de comandas.
            models.Index(fields=["command", "command_status"]),
        ]

    @property
    def pendente(self):
        """Ainda está aberto na comanda — entra na próxima conta."""
        return self.command_status == self.STATUS_PENDENTE

    @property
    def finalizado(self):
        """Já saiu da comanda, cobrado ou não."""
        return self.command_status in self.STATUS_FINALIZADOS
