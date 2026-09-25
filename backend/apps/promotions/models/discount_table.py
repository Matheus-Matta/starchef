from django.db import models
from django.utils import timezone

from apps.core.models import TenantModel


class DiscountTable(TenantModel):
    """A tabela de desconto: um conjunto de regras que vale junto, ou não vale.

    Existe porque promoção real não vem uma a uma. "Happy hour de quinta" são
    seis regras que começam e terminam no mesmo instante, e sem o agrupamento o
    gerente teria de lembrar de desligar as seis — na sexta, uma esquecida
    continua descontando.

    A VALIDADE MORA AQUI. A regra pode ter janela própria, mas a tabela é o
    teto: fora da janela da tabela, nenhuma regra dela vale. É o interruptor
    que uma pessoa apressada consegue achar.
    """

    # Compartilhada entre restaurantes: vazio = a conta inteira, preenchido =
    # só aquela loja. Sobrescreve o FK obrigatório do `TenantModel` — mesmo
    # padrão de `menu.ProductCategory` e `invoices.FiscalProfile`.
    #
    # Sem o opcional, uma rede de dez lojas cadastraria a MESMA promoção dez
    # vezes, e a décima primeira loja abriria sem desconto nenhum.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=140)
    description = models.CharField(max_length=255, blank=True)
    # `is_enabled` é o interruptor da mão humana; `is_active` (propriedade)
    # é a resposta do relógio. São coisas diferentes de propósito: desligar a
    # tabela não apaga a janela, e o gerente pode religá-la sem redigitar datas.
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Interruptor manual. Desligado, nenhuma regra da tabela vale.",
    )
    starts_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Vazio = vale desde sempre.",
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Vazio = não expira.",
    )

    class Meta:
        # A ORDEM É A PRIORIDADE ENTRE TABELAS. Quando duas tabelas alcançam o
        # mesmo produto, a MAIS ANTIGA ganha — foi o que o restaurante prometeu
        # primeiro, e voltar atrás numa promessa antiga por causa de uma nova é
        # o que o cliente percebe como propaganda enganosa.
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_discount_table_per_account",
            ),
        ]
        indexes = [models.Index(fields=["account", "is_enabled"])]

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        """Vale agora? Interruptor ligado E dentro da janela.

        É propriedade, e não campo, porque uma tabela que termina às 18h tem de
        parar de valer às 18h — sem ninguém salvar nada. Um booleano gravado
        precisaria de uma tarefa periódica para virar, e o minuto em que a
        tarefa atrasa é o minuto em que o caixa cobra o preço errado.
        """
        if not self.is_enabled or self.deleted_at is not None:
            return False
        agora = timezone.now()
        if self.starts_at and agora < self.starts_at:
            return False
        if self.ends_at and agora > self.ends_at:
            return False
        return True

    @property
    def status_label(self):
        """O motivo, para a grade não dizer só "inativa"."""
        if self.deleted_at is not None:
            return "Excluída"
        if not self.is_enabled:
            return "Desligada"
        agora = timezone.now()
        if self.starts_at and agora < self.starts_at:
            return "Agendada"
        if self.ends_at and agora > self.ends_at:
            return "Encerrada"
        return "Ativa"
