"""O que SAIU no período: produtos vendidos e baixas de estoque.

Produtos vendidos é a saída que o cliente levou (itens de pedidos pagos).
Baixa de estoque é o que o estoque registrou como saída (venda, consumo de
produção, perda, quebra, validade): o movimento de quantidade negativa.
"""
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import Abs, Coalesce

from apps.reports.comandas_agora import reais
from apps.reports.visao_geral_periodo import faixa

LIMITE = 10


def produtos_vendidos(itens_pagos):
    linhas = (itens_pagos.values("product__name")
              .annotate(quantidade=Sum("quantity"), valor=Sum("total_price"), pedidos=Count("order", distinct=True))
              .order_by("-valor")[:LIMITE])
    return [{"produto": linha["product__name"] or "Sem nome", "quantidade": linha["quantidade"],
             "valor": reais(linha["valor"]), "pedidos": linha["pedidos"]}
            for linha in linhas if (linha["valor"] or 0) > 0]


def baixas_de_estoque(escopo, primeiro, ultimo):
    from apps.stock.models import StockMovement

    escopo_estoque = {k: v for k, v in escopo.items() if k in ("account_id", "restaurant_id")}
    linhas = (
        StockMovement.objects.filter(**escopo_estoque, quantity__lt=0,
                                     **faixa("created_at", primeiro, ultimo))
        .annotate(nome=Coalesce("ingredient__name", "product__name"),
                  unidade=Coalesce("ingredient__unit", "stock_unit"))
        .values("nome", "unidade", "movement_type")
        .annotate(quantidade=Sum(Abs(F("quantity"))), custo=Sum(Abs(F("total_cost"))))
        .order_by("-custo", "-quantidade")[:LIMITE]
    )
    return [{"item": linha["nome"] or "Sem nome", "unidade": linha["unidade"] or "",
             "tipo": linha["movement_type"], "quantidade": linha["quantidade"],
             "custo": reais(linha["custo"] or Decimal("0"))}
            for linha in linhas if linha["quantidade"]]
