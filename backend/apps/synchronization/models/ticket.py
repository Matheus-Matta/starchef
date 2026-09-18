"""Bilhete de matrícula: um segredo que vale UMA vez e por pouco tempo.

O que existia antes — e continua existindo — é o `SYNC_ENROLL_SECRET`: uma
string combinada, fixa, que cifra o pacote de credenciais na volta. Ela nunca
foi suficiente sozinha para matricular nada (a rota também exige usuário e
senha de admin da conta, e o `account_id`), e é por isso que a revisão externa
exagerou ao classificar o ponto como crítico.

Mas ela tem dois defeitos que o tempo agrava:

1. **Não expira.** Uma vez combinada, vale para sempre. Quem instalou a loja em
   março continua com ela em dezembro, e ela passou por um grupo de WhatsApp no
   caminho — que é exatamente o problema que a matrícula automática existia para
   resolver.
2. **Não tem dono.** Não dá para responder "quem usou, quando, para qual loja",
   porque não há nada para olhar.

O bilhete resolve os dois: nasce na nuvem para UMA loja, morre ao ser usado ou
no prazo, e deixa registro de quem o emitiu e de qual nó saiu dele.

O código em claro existe uma única vez, no momento da emissão. Aqui fica só o
hash — mesma disciplina do token do nó.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import UUIDModel


class SyncEnrollmentTicketQuerySet(models.QuerySet):
    def utilizaveis(self):
        return self.filter(used_at__isnull=True, expires_at__gt=timezone.now())


class SyncEnrollmentTicket(UUIDModel):
    """Um convite de matrícula, para uma conta, com prazo."""

    #: Prazo padrão. Curto de propósito: o bilhete é emitido no momento em que
    #: alguém vai instalar a loja, não guardado para depois.
    VALIDADE_PADRAO_MINUTOS = 30

    account = models.ForeignKey(
        "accounts.Account", related_name="sync_enrollment_tickets", on_delete=models.CASCADE
    )
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        related_name="sync_enrollment_tickets",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    code_hash = models.CharField(max_length=64, unique=True, editable=False)
    label = models.CharField(max_length=120, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="sync_enrollment_tickets",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)

    used_at = models.DateTimeField(null=True, blank=True)
    used_by_node = models.ForeignKey(
        "synchronization.SyncNode",
        related_name="enrollment_tickets",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    used_from_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = SyncEnrollmentTicketQuerySet.as_manager()

    class Meta:
        verbose_name = "Bilhete de matrícula"
        verbose_name_plural = "Bilhetes de matrícula"
        ordering = ["-created_at"]

    def __str__(self):
        estado = "usado" if self.used_at else ("vencido" if self.vencido else "aberto")
        return f"{self.label or self.account_id} [{estado}]"

    @property
    def vencido(self):
        return timezone.now() >= self.expires_at

    @property
    def utilizavel(self):
        return self.used_at is None and not self.vencido

    @classmethod
    def novo_codigo(cls):
        """O código em claro. Existe uma vez só, na resposta da emissão."""
        return f"sc-{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"
