"""Cardápio de consumo: o que sai do estoque sozinho, no dia certo.

O buffet repete o cardápio — segunda uma coisa, terça outra — e todo dia gasta
arroz, óleo e sal. Lançar essa saída à mão todo dia é o que este app
substitui. O cardápio diz O QUE sai, DE ONDE e QUANDO; cada execução vira uma
saída de estoque comum (`stock.StockExit`), com lote, custo e histórico.
"""
from datetime import time

from django.db import models
from django.utils import timezone

from apps.core.models import TenantModel


class CardapioConsumo(TenantModel):
    DIARIA = "daily"
    SEMANAL = "weekly"
    MENSAL = "monthly"
    FREQUENCIA_CHOICES = [(DIARIA, "Todo dia"), (SEMANAL, "Toda semana"), (MENSAL, "Todo mês")]

    nome = models.CharField(max_length=120)
    frequencia = models.CharField(max_length=10, choices=FREQUENCIA_CHOICES, default=DIARIA)
    # 0 = segunda ... 6 = domingo, como `date.weekday()`. Lista: "segunda a
    # sexta" é um cardápio só, não cinco.
    dias_da_semana = models.JSONField(default=list, blank=True)
    # 31 em fevereiro vira o último dia do mês (`agenda.py`).
    dia_do_mes = models.PositiveSmallIntegerField(null=True, blank=True)
    horario = models.TimeField(default=time(6, 0))
    local = models.ForeignKey("stock.StockLocation", related_name="cardapios_consumo", on_delete=models.PROTECT)
    # Ligado: a saída é confirmada sozinha. Desligado: fica em rascunho para
    # alguém conferir a quantidade do dia — buffet por quilo varia.
    confirma_sozinho = models.BooleanField(default=False)
    comeca_em = models.DateField(default=timezone.localdate)
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(dia_do_mes__isnull=True) | models.Q(dia_do_mes__gte=1, dia_do_mes__lte=31),
                name="cardapio_consumo_dia_do_mes_valido",
            ),
        ]

    def __str__(self):
        return self.nome


class ItemCardapioConsumo(TenantModel):
    """Um insumo (na unidade dele ou numa compatível) ou um produto.

    O produto sai pela ficha técnica — `quantidade` é quantos rendimentos da
    ficha —, ou pelo insumo direto do cadastro, igual à baixa da venda.
    """

    cardapio = models.ForeignKey(CardapioConsumo, related_name="itens", on_delete=models.CASCADE)
    ingredient = models.ForeignKey(
        "menu.Ingredient", null=True, blank=True, related_name="itens_cardapio_consumo", on_delete=models.PROTECT
    )
    product = models.ForeignKey(
        "menu.Product", null=True, blank=True, related_name="itens_cardapio_consumo", on_delete=models.PROTECT
    )
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    unidade = models.CharField(max_length=12, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(ingredient__isnull=False, product__isnull=True)
                           | models.Q(ingredient__isnull=True, product__isnull=False)),
                name="item_cardapio_consumo_insumo_ou_produto",
            ),
            models.CheckConstraint(condition=models.Q(quantidade__gt=0), name="item_cardapio_consumo_quantidade_positiva"),
        ]

    def __str__(self):
        return f"{self.ingredient or self.product} x {self.quantidade}"


class ExecucaoCardapio(TenantModel):
    """Um cardápio executado num dia. Um por dia, garantido pelo BANCO.

    A trava é o índice único, não um `if`: o worker que reinicia no meio, ou
    dois workers no mesmo minuto, esbarram no INSERT e não baixam duas vezes.
    """

    CONFIRMADA = "posted"
    PARA_CONFERIR = "draft"
    SEM_SALDO = "no_stock"
    FALHOU = "failed"
    SITUACAO_CHOICES = [
        (CONFIRMADA, "Baixa confirmada"),
        (PARA_CONFERIR, "Saída para conferir"),
        (SEM_SALDO, "Sem saldo para baixar"),
        (FALHOU, "Falhou"),
    ]

    cardapio = models.ForeignKey(CardapioConsumo, related_name="execucoes", on_delete=models.PROTECT)
    data = models.DateField()
    saida = models.ForeignKey(
        "stock.StockExit", null=True, blank=True, related_name="execucoes_cardapio", on_delete=models.SET_NULL
    )
    situacao = models.CharField(max_length=10, choices=SITUACAO_CHOICES)
    # [{"ingredient", "nome", "unidade", "pedido", "baixado", "faltou"}]
    faltas = models.JSONField(default=list, blank=True)
    mensagem = models.TextField(blank=True)

    class Meta:
        ordering = ["-data", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["cardapio", "data"], name="uma_execucao_por_cardapio_por_dia"),
        ]

    def __str__(self):
        return f"{self.cardapio} em {self.data:%d/%m/%Y}"
